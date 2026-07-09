import { useState } from "react";
import { CheckIcon, ClipboardIcon } from "lucide-react";
import {
	getSectionTitle,
	groupAndOrderChanges,
	isSectionCollapsible,
} from "../utils";
import type { Change } from "../utils";
import { cn } from "@opencut/utils/ui";
import { Button } from "@opencut/components/ui/button";
import { useOpencutT } from "@opencut/i18n/useOpencutT";

/** 将更新日志条目组装为 Markdown 文本。 */
function buildMarkdown({
	description,
	changes,
}: {
	description?: string;
	changes: Change[];
}): string {
	const lines: string[] = [];

	if (description) {
		lines.push(description, "");
	}

	const { grouped, orderedTypes } = groupAndOrderChanges({ changes });

	for (const type of orderedTypes) {
		if (isSectionCollapsible({ type })) {
			lines.push(
				buildCollapsibleMarkdownSection({
					title: getSectionTitle({ type }),
					changes: grouped[type],
				}),
				"",
			);
			continue;
		}

		lines.push(`## ${getSectionTitle({ type })}`);
		for (const change of grouped[type]) {
			lines.push(`- ${change.text}`);
		}
		lines.push("");
	}

	return lines.join("\n").trimEnd();
}

/** 构建可折叠 Markdown 区块。 */
function buildCollapsibleMarkdownSection({
	title,
	changes,
}: {
	title: string;
	changes: Change[];
}): string {
	const bulletLines = changes.map((change) => `- ${change.text}`).join("\n");

	return `<details>\n<summary>${title}</summary>\n\n${bulletLines}\n\n</details>`;
}

/** 复制更新日志 Markdown 到剪贴板。 */
export function CopyMarkdownButton({
	description,
	changes,
}: {
	description?: string;
	changes: Change[];
}) {
	const { tDialogs } = useOpencutT();
	const [copied, setCopied] = useState(false);

	const handleCopy = async () => {
		const markdown = buildMarkdown({ description, changes });
		await navigator.clipboard.writeText(markdown);
		setCopied(true);
		setTimeout(() => setCopied(false), 2000);
	};

	return (
		<Button
			size="sm"
			variant="text"
			onClick={handleCopy}
			className={cn(
				"flex items-center gap-1.5",
				copied && "pointer-events-none",
			)}
			title={tDialogs("copyAsMarkdownTitle")}
		>
			{copied ? (
				<CheckIcon className="size-4" />
			) : (
				<ClipboardIcon className="size-4" />
			)}
			{copied ? tDialogs("copied") : tDialogs("copyAsMarkdown")}
		</Button>
	);
}
