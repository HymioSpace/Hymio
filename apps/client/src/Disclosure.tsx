import { useEffect, useId, useState, type HTMLAttributes, type ReactNode } from 'react';

/** Keep content mounted through the grid transition; closed content cannot receive focus. */
export function Disclosure({
  summary,
  children,
  resetKey,
  className = '',
  ...props
}: {
  summary: ReactNode;
  children: ReactNode;
  resetKey?: string | boolean;
} & HTMLAttributes<HTMLDivElement>) {
  const id = useId();
  const [expanded, setExpanded] = useState(false);
  useEffect(() => setExpanded(false), [resetKey]);
  return (
    <div {...props} className={`${className} disclosure`} data-expanded={expanded}>
      <button
        type="button"
        className="disclosure-toggle"
        aria-expanded={expanded}
        aria-controls={id}
        onClick={() => setExpanded((value) => !value)}
      >
        {summary}
      </button>
      <div id={id} className="disclosure-grid" aria-hidden={!expanded} inert={!expanded}>
        <div className="disclosure-content">{children}</div>
      </div>
    </div>
  );
}
