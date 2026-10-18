import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

/** 확인 팝업이 떠 있을 때 그 글을 돌려주고, 확인 또는 취소를 누른다. */
export async function answerConfirm(ok: boolean): Promise<string> {
  const dialog = await screen.findByRole("alertdialog");
  const text = dialog.querySelector(".confirm-message")?.textContent ?? "";
  await userEvent.click(within(dialog).getByRole("button", { name: ok ? "확인" : "취소" }));
  return text;
}
