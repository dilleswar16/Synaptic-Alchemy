/** One "new chat" of the chat page: `serial` makes each a fresh conversation component, `startedConversationId` is the conversation its first question created. */
export interface NewChatSession {
  serial: number;
  startedConversationId: string | null;
}

/**
 * The key of the conversation component for the address the page is at. A new chat, and the conversation that new chat just created, share one key: the
 * component that asked the first question keeps its live answer while the address changes to the conversation. Any other conversation is its own component.
 */
export function conversationKeyFor(addressConversationId: string | undefined, session: NewChatSession): string {
  return addressConversationId === undefined || addressConversationId === session.startedConversationId ? `new-${session.serial}` : addressConversationId;
}
