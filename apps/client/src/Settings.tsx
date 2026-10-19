import { X } from 'lucide-react';
import type { LoginState } from './useLogin';
import { DeviceManager } from './DeviceManager';
import { Button, Companion, IconButton, Sheet } from '@hymio/ui';
export function Settings({ login, onClose }: { login: LoginState; onClose: () => void }) {
  return (
    <Sheet className="settings-dialog" labelledBy="settings-title" onClose={onClose}>
      <div className="dialog-head">
        <Companion compact />
        <IconButton label="关闭账号设置" onClick={onClose}>
          <X size={19} />
        </IconButton>
      </div>
      <h2 id="settings-title">我的账号</h2>
      <p className="dialog-intro">{login.session?.name}</p>
      <p className="dialog-note">在不同设备上，继续同一段对话。</p>
      <DeviceManager login={login} />
      {login.error && (
        <p role="alert" className="form-error">
          {login.error}
        </p>
      )}
      <Button variant="quiet" busy={login.busy} onClick={() => void login.logout()}>
        退出登录
      </Button>
    </Sheet>
  );
}
