/** 应用装配错误：凭证/配置缺失时抛这个，便于 CLI 明确提示。 */
export declare class AppError extends Error {
    constructor(message: string);
}
