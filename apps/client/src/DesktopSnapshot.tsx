import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

export function DesktopSnapshot({ src, onClose }: { src: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return createPortal(
    <dialog
      className="desktop-view"
      ref={dialog}
      aria-label="桌面快照"
      onCancel={(event) => {
        event.stopPropagation();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === dialog.current) onClose();
      }}
    >
      <header>
        <strong>桌面快照</strong>
        <button onClick={onClose}>关闭</button>
      </header>
      <img src={src} alt="放大的云电脑桌面快照" />
    </dialog>,
    document.body,
  );
}
