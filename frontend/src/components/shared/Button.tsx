import { ButtonHTMLAttributes, forwardRef } from 'react';
import { cn } from '@/lib/utils';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', loading, disabled, children, ...props }, ref) => {
    const baseStyles =
      'inline-flex items-center justify-center font-medium transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed';

    const variantStyles = {
      primary:
        'bg-primary text-white hover:bg-primary-hover focus:ring-primary shadow-sm hover:shadow-md hover:-translate-y-0.5',
      secondary:
        'bg-surface text-foreground hover:bg-surface-secondary border border-border focus:ring-primary',
      outline:
        'bg-transparent text-foreground border border-border hover:bg-surface focus:ring-primary',
      ghost: 'bg-transparent text-foreground hover:bg-surface focus:ring-primary',
      danger:
        'bg-danger text-white hover:bg-red-600 focus:ring-danger shadow-sm hover:shadow-md hover:-translate-y-0.5',
    };

    const sizeStyles = {
      sm: 'px-3 py-1.5 text-sm rounded-full',
      md: 'px-5 py-2.5 text-base rounded-full',
      lg: 'px-6 py-3 text-lg rounded-full',
    };

    return (
      <button
        ref={ref}
        className={cn(baseStyles, variantStyles[variant], sizeStyles[size], className)}
        disabled={disabled || loading}
        {...props}
      >
        {loading && (
          <svg
            className="animate-spin -ml-1 mr-2 h-4 w-4"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        )}
        {children}
      </button>
    );
  }
);

Button.displayName = 'Button';
