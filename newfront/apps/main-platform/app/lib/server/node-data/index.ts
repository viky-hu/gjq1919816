import type { AddClusterFileBody, ClusterFile } from "@/app/lib/cluster-files-contract";
import type { Cluster, DatabaseUpdate, Metrics } from "@/app/lib/database-types";
import type { NodeRetrieveResponse } from "@/app/lib/node-retrieve-contract";
import {
  addCluster,
  addClusterFile,
  deleteCluster,
  deleteClusterFile,
  getClusterFile,
  getClusters,
  getMetrics,
  getUpdateLog,
  listClusterFiles,
  renameCluster,
} from "@/app/lib/database-store";

const DEFAULT_ACCOUNT = "本机节点";
const MAX_UPDATES = 200;

function normalizeAccount(rawAccount?: string | null, fallbackActor?: string | null): string {
  const fromAccount = rawAccount?.trim() ?? "";
  if (fromAccount) return fromAccount;
  const fromActor = fallbackActor?.trim() ?? "";
  if (fromActor) return fromActor;
  return DEFAULT_ACCOUNT;
}

function tokenizeQuestion(question: string): string[] {
  return question
    .trim()
    .split(/[\s,，。！？；：、()（）\[\]{}“”"'`<>《》]+/)
    .map((token) => token.trim().toLowerCase())
    .filter((token) => token.length >= 2);
}

function scoreText(text: string, tokens: string[]): number {
  const lower = text.toLowerCase();
  return tokens.reduce((score, token) => score + (lower.includes(token) ? 1 : 0), 0);
}

export function resolveNodeAccount(input: { account?: string | null; actor?: string | null }): string {
  return normalizeAccount(input.account, input.actor);
}

export async function listNodeClusters(account: string): Promise<Cluster[]> {
  void account;
  return getClusters();
}

export async function createNodeCluster(args: {
  account: string;
  name: string;
  actor?: string;
}): Promise<Cluster> {
  void args.account;
  return addCluster(args.name, args.actor);
}

export async function renameNodeCluster(args: {
  account: string;
  clusterId: string;
  name: string;
  actor?: string;
}): Promise<Cluster | null> {
  void args.account;
  return renameCluster(args.clusterId, args.name, args.actor);
}

export async function deleteNodeCluster(args: {
  account: string;
  clusterId: string;
  actor?: string;
}): Promise<boolean> {
  void args.account;
  return deleteCluster(args.clusterId, args.actor);
}

export async function listNodeClusterFiles(args: {
  account: string;
  clusterId: string;
}): Promise<ClusterFile[]> {
  void args.account;
  return listClusterFiles(args.clusterId);
}

export async function getNodeClusterFile(args: {
  account: string;
  clusterId: string;
  fileId: string;
}): Promise<ClusterFile | null> {
  void args.account;
  return getClusterFile(args.clusterId, args.fileId);
}

export async function addNodeClusterFile(args: {
  account: string;
  clusterId: string;
  actor?: string;
  body: AddClusterFileBody;
}): Promise<ClusterFile> {
  void args.account;
  return addClusterFile(args.clusterId, args.body, args.actor);
}

export async function deleteNodeClusterFile(args: {
  account: string;
  clusterId: string;
  fileId: string;
  actor?: string;
}): Promise<boolean> {
  void args.account;
  return deleteClusterFile(args.clusterId, args.fileId, args.actor);
}

export async function getNodeMetrics(account: string): Promise<Metrics> {
  void account;
  return getMetrics();
}

export async function listNodeUpdates(account: string, limit: number = MAX_UPDATES): Promise<DatabaseUpdate[]> {
  void account;
  return getUpdateLog().slice(0, Math.max(1, Math.min(limit, MAX_UPDATES))) as DatabaseUpdate[];
}

export async function retrieveNodeAnswer(args: {
  account: string;
  question: string;
}): Promise<Omit<NodeRetrieveResponse, "requestId">> {
  void args.account;
  const question = args.question.trim();
  if (!question) {
    return { status: "error", answer: "问题不能为空", details: [] };
  }

  const tokens = tokenizeQuestion(question);
  const details = getClusters()
    .flatMap((cluster) =>
      listClusterFiles(cluster.id).map((file) => {
        const content = file.textContent ?? file.name;
        return {
          clusterId: cluster.id,
          fileId: file.id,
          fileName: file.name,
          score: scoreText(`${file.name}\n${content}`, tokens),
          snippet: content.slice(0, 220),
        };
      }),
    )
    .sort((a, b) => b.score - a.score)
    .slice(0, 5);

  const matched = details.filter((item) => item.score > 0);
  const selected = matched.length > 0 ? matched : details.slice(0, 3);
  if (selected.length === 0) {
    return {
      status: "error",
      answer: "当前演示数据库暂无可检索文献，请先上传文件。",
      details: [],
    };
  }

  return {
    status: "ok",
    answer:
      matched.length > 0
        ? `演示模式已在本地文献中找到 ${matched.length} 条相关片段。`
        : "演示模式未命中高相关片段，已返回最近文献供参考。",
    details: selected,
    confidence: matched.length > 0 ? 0.78 : 0.42,
  };
}

export async function recordNodeAdminAction(args: {
  account: string;
  actor?: string;
  requestType: string;
  remark?: string;
}) {
  void args.account;
  void args.actor;
  void args.remark;
  return {
    ok: true,
    action: `管理员动作：${args.requestType}`,
  };
}
