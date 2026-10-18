import { useEffect, useRef } from 'react';
import { X, UserRound, LoaderCircle } from 'lucide-react';
import type { LoginState } from './useLogin';
export function Settings({ login, onClose }: { login: LoginState; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      className="settings-dialog"
      ref={dialog}
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === dialog.current) onClose();
      }}
      aria-labelledby="settings-title"
    >
      <div className="dialog-head">
        <span className="dialog-symbol">
          <UserRound size={22} />
        </span>
        <button className="icon-button" aria-label="关闭账号设置" onClick={onClose}>
          <X size={19} />
        </button>
      </div>
      <h2 id="settings-title">我的账号</h2>
      <p className="dialog-intro">{login.session?.name}</p>
      <p className="dialog-note">在不同设备上，继续同一段对话。</p>
      {login.error && (
        <p role="alert" className="form-error">
          {login.error}
        </p>
      )}
      <button className="primary-button" disabled={login.busy} onClick={() => void login.logout()}>
        {login.busy && <LoaderCircle className="spin" size={17} />}退出登录
      </button>
    </dialog>
  );
}
