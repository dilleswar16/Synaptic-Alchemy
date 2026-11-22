/** The question typed on Home arrives as router state (`navigate("/chat", { state: { question } })`); anything else in the state, or a blank question, is not one. */
export function readHomeQuestion(routerState: unknown): string | undefined {
  const question = typeof routerState === "object" && routerState !== null && "question" in routerState ? routerState.question : undefined;
  return typeof question === "string" && question.trim() !== "" ? question.trim() : undefined;
}
