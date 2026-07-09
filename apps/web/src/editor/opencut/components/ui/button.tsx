import * as React from "react";
import { Slot as SlotPrimitive } from "radix-ui";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@opencut/utils/ui";

/** OpenCut 按钮样式变体（对齐 SVF 工作台主色与中性灰）。 */
const buttonVariants = cva(
	"inline-flex items-center cursor-pointer justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
	{
		variants: {
			variant: {
				default:
					"bg-primary text-primary-foreground hover:bg-primary/90 border border-transparent",
				background:
					"bg-background text-foreground hover:bg-muted/60 border border-border",
				destructive:
					"bg-destructive text-destructive-foreground hover:bg-destructive/80",
				"destructive-foreground":
					"border border-border bg-background hover:bg-destructive/15 text-destructive",
				caution: "text-caution hover:bg-caution/10",
				outline:
					"border border-border bg-background text-foreground hover:bg-muted/50",
				secondary:
					"bg-secondary text-secondary-foreground border border-secondary-border hover:bg-muted/60",
				text: "bg-transparent rounded-none opacity-100 hover:opacity-75 text-foreground",
				ghost: "bg-transparent text-foreground hover:bg-muted/50",
				link: "text-primary underline-offset-4 hover:underline !p-0 !h-auto",
			},
			size: {
				default: "h-9 px-4 py-2",
				sm: "h-7 p-1 px-2.5 text-sm rounded-sm",
				lg: "h-10 p-5 px-6",
				icon: "size-7 rounded-sm",
				text: "p-0",
			},
		},
		defaultVariants: {
			variant: "default",
			size: "default",
		},
	},
);

export interface ButtonProps
	extends React.ButtonHTMLAttributes<HTMLButtonElement>,
		VariantProps<typeof buttonVariants> {
	asChild?: boolean;
}

/** 通用按钮组件，支持多种视觉变体与尺寸。 */
const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
	({ className, variant, size, asChild = false, ...props }, ref) => {
		const Comp = asChild ? SlotPrimitive.Slot : "button";
		const effectiveSize = size ?? (variant === "text" ? "text" : "default");
		return (
			<Comp
				className={cn(
					buttonVariants({ variant, size: effectiveSize, className }),
				)}
				ref={ref}
				type="button"
				{...props}
			/>
		);
	},
);
Button.displayName = "Button";

export { Button, buttonVariants };
