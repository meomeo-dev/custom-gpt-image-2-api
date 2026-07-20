// GPT-Image 配置节点安全扩展 (security extension)
//
// 问题 (bug)：ComfyUI 保存/导出工作流时，会把节点所有 widget 的值写进
// workflow JSON 的 widgets_values 数组（导出 PNG 时也内嵌同一份 workflow）。
// 因此「GPT-Image API 配置」节点里的「密钥」(api_key) 会随工作流一起落盘，
// 分享 / 上传 / 截图工作流就会连同密钥一起泄露。
//
// 关键约束：ComfyUI 里「保存(Ctrl+S)」「导出」「输出图内嵌 workflow」三者
// 都走同一个 graph.serialize()，前端没有可靠的「只在导出时剔除、保存时保留」
// 的钩子。所以不去区分保存/导出，而是双管齐下：
//
//   1) 密钥 widget 设 widget.serialize = false —— 密钥永不写进 widgets_values，
//      任何序列化产物(本地保存的 .json、导出、PNG 内嵌)都不含它。
//      注意：这是 widget 自身属性(控制持久化)，不是 options.serialize
//      (控制是否随 prompt 发给后端执行)——后者不动，密钥照常参与执行。
//
//   2) 密钥单独存进浏览器 localStorage，按 base_url 归档 —— 重开工作流时
//      自动回填，本机免重填；但它不进工作流 JSON，分享时不泄露。
//
// 权衡 (tradeoff)：localStorage 是明文存在浏览器 profile 里，同源 JS 可读、
// 也留在磁盘。它严格优于「写进会被分享的工作流」，是社区处理前端密钥的
// 标准做法，但不是加密保险箱。想要更强隔离可改存服务端本地配置文件。

import { app } from "../../scripts/app.js";

// 配置节点内部 key（见 __init__.py 的 NODE_CLASS_MAPPINGS）。
const CONFIG_NODE = "ImageAPIConfig";
// widget 名（见 config_node.py 的 INPUT_TYPES）。
const SECRET_WIDGET = "密钥";
const BASEURL_WIDGET = "接口地址";
// localStorage 键前缀；按 base_url 归档，可支持多网关各自的密钥，
// 且不依赖节点 id（ComfyUI 节点 id 会跨工作流碰撞，见 docs 第 6 节）。
const LS_PREFIX = "meomeo-dev.gpt-image.apikey::";

// 与后端 config_node.build 的归一化保持一致：去空白、去末尾斜杠。
// 保证「存」和「取」用的键一致，无论用户填了几个尾斜杠。
function normalizeBaseUrl(v) {
    return (v || "").trim().replace(/\/+$/, "");
}

function lsKey(baseUrl) {
    const b = normalizeBaseUrl(baseUrl);
    return b ? LS_PREFIX + b : null;
}

function saveKey(baseUrl, apiKey) {
    const k = lsKey(baseUrl);
    if (!k) return;
    try {
        if (apiKey) {
            localStorage.setItem(k, apiKey);
        } else {
            // 用户清空了密钥 → 同步删除本机存档，避免残留。
            localStorage.removeItem(k);
        }
    } catch (e) {
        console.error("[GPT-Image] 无法写入本机密钥存档：", e);
    }
}

function loadKey(baseUrl) {
    const k = lsKey(baseUrl);
    if (!k) return null;
    try {
        return localStorage.getItem(k);
    } catch (e) {
        console.error("[GPT-Image] 无法读取本机密钥存档：", e);
        return null;
    }
}

app.registerExtension({
    name: "meomeo-dev.gpt-image.config-security",

    async beforeRegisterNodeDef(nodeType, nodeData /*, app */) {
        if (nodeData?.name !== CONFIG_NODE) return;

        // 从本机存档回填密钥：base_url 非空、且当前密钥为空时才填，
        // 不覆盖用户手动输入的值。
        const restoreKey = (node) => {
            const baseW = node.widgets?.find((x) => x?.name === BASEURL_WIDGET);
            const keyW = node.widgets?.find((x) => x?.name === SECRET_WIDGET);
            if (!baseW || !keyW) return;
            if (keyW.value) return; // 已有值，不覆盖
            const stored = loadKey(baseW.value);
            if (stored) {
                node.__restoringKey = true; // 防止回填触发保存回环
                keyW.value = stored;
                node.__restoringKey = false;
                app.graph?.setDirtyCanvas(true, true);
            }
        };

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const ret = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            try {
                const keyW = this.widgets?.find((x) => x?.name === SECRET_WIDGET);
                const baseW = this.widgets?.find((x) => x?.name === BASEURL_WIDGET);

                if (keyW) {
                    // (1) 阻止密钥写进 widgets_values（保存/导出/PNG 内嵌都不含它）。
                    keyW.serialize = false;

                    // 密钥变化 → 存进本机存档（回填过程中不重复存）。
                    const origKeyCb = keyW.callback;
                    keyW.callback = function (value) {
                        const r = origKeyCb ? origKeyCb.apply(this, arguments) : undefined;
                        if (!this.__restoringKey) {
                            saveKey(baseW?.value, value);
                        }
                        return r;
                    }.bind(this);
                }

                if (baseW) {
                    // base_url 变化 → 尝试用新地址的存档回填密钥
                    // （新建节点时先填地址、再自动带出对应密钥）。
                    const origBaseCb = baseW.callback;
                    baseW.callback = function (value) {
                        const r = origBaseCb ? origBaseCb.apply(this, arguments) : undefined;
                        restoreKey(this);
                        return r;
                    }.bind(this);
                }
            } catch (e) {
                console.error("[GPT-Image] 配置节点安全扩展初始化失败：", e);
            }
            return ret;
        };

        // 载入工作流后（widgets_values 已应用、base_url 已就位）回填密钥。
        // configure() 会先套用 widget 值再调 onConfigure，故此时 base_url 可用。
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info) {
            const ret = onConfigure ? onConfigure.apply(this, arguments) : undefined;
            try {
                restoreKey(this);
            } catch (e) {
                console.error("[GPT-Image] 载入后回填密钥失败：", e);
            }
            return ret;
        };
    },
});
