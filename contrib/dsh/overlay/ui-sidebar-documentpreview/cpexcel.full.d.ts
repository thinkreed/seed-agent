/** 声明 xlsx 的 cpexcel 子路径（@e965/xlsx 未带该子路径的类型；运行时是 codepage 表）。 */
declare module 'xlsx/dist/cpexcel.full.mjs' {
  const codepages: Record<string, unknown>
  export = codepages
}