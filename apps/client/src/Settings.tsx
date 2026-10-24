import { ModelSettings } from './ModelSettings';
import { displayName } from './HomePanel';
import { Activity, X } from 'lucide-react';
import type { LoginState } from './useLogin';
import { DeviceManager } from './DeviceManager';
import { Button, Companion, IconButton, Sheet } from '@hymio/ui';
export function Settings({
  login,
  onClose,
  onTrace,
}: {
  login: LoginState;
  onClose: () => void;
  onTrace: () => void;
}) {
  return (
    <Sheet className="settings-dialog" labelledBy="settings-title" onClose={onClose}>
      <div className="dialog-head">
        <Companion compact />
        <IconButton label="关闭账号设置" onClick={onClose}>
          <X size={19} />
        </IconButton>
      </div>
      <h2 id="settings-title">账号与偏好</h2>
      <p className="dialog-intro">{displayName(login.session?.name)}</p>
      <p className="dialog-note">在不同设备上，继续同一段对话。</p>
      <ModelSettings login={login} />
      <DeviceManager login={login} />
      {login.error && (
        <p role="alert" className="form-error">
          {login.error}
        </p>
      )}
      <button className="settings-trace" onClick={onTrace}>
        <Activity size={16} />
        工作记录与连接诊断
      </button>
      <Button variant="quiet" busy={login.busy} onClick={() => void login.logout()}>
        退出登录
      </Button>
    </Sheet>
  );
}
