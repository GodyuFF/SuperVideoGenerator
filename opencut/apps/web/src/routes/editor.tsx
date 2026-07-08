import { createFileRoute } from "@tanstack/react-router";
import { EditorPage } from "../editor/editor-page";

export const Route = createFileRoute("/editor")({ component: EditorPage });
