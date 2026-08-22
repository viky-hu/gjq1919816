export type LoginLoadingTip = {
  id: string;
  text: string;
};

export const LOGIN_LOADING_TIPS: readonly LoginLoadingTip[] = [
  {
    id: "federated-data",
    text: "正在拉取最新联邦数据，校准本次协同检索的上下文",
  },
  {
    id: "model-access",
    text: "正在查看 MiA-EMB 与大模型接入情况，确认推理链路可用",
  },
  {
    id: "knowledge-visualization",
    text: "正在加载知识图谱与可视化图表，整理首屏展示数据",
  },
  {
    id: "workspace",
    text: "正在初始化主页面工作区，准备进入多节点协同检索",
  },
] as const;
