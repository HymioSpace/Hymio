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
      aria-label="图片预览"
      onCancel={(event) => {
        event.stopPropagation();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === dialog.current) onClose();
      }}
    >
      <header>
        <strong>图片预览</strong>
        <button onClick={onClose}>关闭</button>
      </header>
      <img src={src} alt="完整图片" />
    </dialog>,
    document.body,
  );
}
