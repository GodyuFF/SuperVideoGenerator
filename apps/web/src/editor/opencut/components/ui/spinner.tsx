import { HugeiconsIcon, type HugeiconsIconProps } from "@hugeicons/react";
import { Loading03Icon } from "@hugeicons/core-free-icons";
import { cn } from "@opencut/utils/ui";
import { useOpencutT } from "@opencut/i18n/useOpencutT";

/** 加载中旋转指示器。 */
function Spinner({ className, ...props }: Omit<HugeiconsIconProps, "icon">) {
	const { tCommon } = useOpencutT();

	return (
		<HugeiconsIcon
			icon={Loading03Icon}
			role="status"
			aria-label={tCommon("loading")}
			className={cn("size-4 animate-spin", className)}
			{...props}
		/>
	);
}

export { Spinner };
