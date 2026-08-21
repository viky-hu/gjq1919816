import type {
  AppendMessagesInput,
  ChatConversationDetail,
  ChatConversationSummary,
  CreateConversationInput,
} from "@/app/lib/chat-history-contract";
import { getDefaultChatHistoryStorageMode } from "../offline-demo";
import { MockChatHistory } from "./mock-storage";

type StorageMode = "auto" | "mock" | "prisma";
const STORAGE_MODE: StorageMode = getDefaultChatHistoryStorageMode(process.env.CHAT_HISTORY_STORAGE_MODE);

export function isMockMode(): boolean {
  return true;
}

export function getStorageMode(): StorageMode {
  return STORAGE_MODE;
}

export function buildConversationTitle(firstUserMessage: string): string {
  const trimmed = firstUserMessage.trim().replace(/\s+/g, " ");
  if (trimmed.length <= 15) return trimmed;
  return trimmed.slice(0, 15) + "...";
}

export async function listAllConversations(
  ownerAccount: string = "default",
): Promise<ChatConversationSummary[]> {
  void ownerAccount;
  return MockChatHistory.listAllConversations();
}

export async function getConversationWithMessages(
  id: string,
): Promise<ChatConversationDetail | null> {
  return MockChatHistory.getConversationWithMessages(id);
}

export async function createConversation(
  input: CreateConversationInput,
  ownerAccount: string = "default",
): Promise<ChatConversationSummary> {
  void ownerAccount;
  return MockChatHistory.createConversation(input);
}

export async function appendMessages(
  conversationId: string,
  input: AppendMessagesInput,
): Promise<void> {
  return MockChatHistory.appendMessages(conversationId, input);
}

export async function deleteConversation(id: string): Promise<void> {
  return MockChatHistory.deleteConversation(id);
}
