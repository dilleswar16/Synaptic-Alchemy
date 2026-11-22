import { describe, expect, it } from "vitest";
import { conversationKeyFor, type NewChatSession } from "./conversationKey";

const session: NewChatSession = { serial: 2, startedConversationId: null };

describe("conversationKeyFor", () => {
  it("gives a new chat the key of its serial", () => {
    expect(conversationKeyFor(undefined, session)).toBe("new-2");
  });

  it("keeps the key when the address moves to the conversation the new chat just created, so the component keeps its answer", () => {
    expect(conversationKeyFor("c-1", { ...session, startedConversationId: "c-1" })).toBe(conversationKeyFor(undefined, session));
  });

  it("gives any other conversation its own key, so opening it from the list starts a fresh component", () => {
    expect(conversationKeyFor("c-9", { ...session, startedConversationId: "c-1" })).toBe("c-9");
    expect(conversationKeyFor("c-9", session)).toBe("c-9");
  });

  it("gives the next new chat a different key than the one before it", () => {
    expect(conversationKeyFor(undefined, { serial: 3, startedConversationId: null })).not.toBe(conversationKeyFor(undefined, session));
  });
});
