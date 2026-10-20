import type { Approval, Message, ToolActivity } from '@hymio/client';
import { groupMessages, ToolActivityGroup } from './ToolActivityGroup';
import { MessageView } from './MessageView';
import type { LoginState } from './useLogin';

function isToolRun(group: Message[]): boolean {
  const head = group[0];
  return head.role === 'assistant' && !head.content.trim() && !!head.calls?.length;
}

/** 一串消息的常规排版：连续的工具调用合成一组，其余按普通消息渲染。 */
export function ActivityStream({
  messages,
  tools,
  login,
  approvals,
  onAction,
}: {
  messages: Message[];
  tools: ToolActivity[];
  login: LoginState;
  approvals?: Approval[];
  onAction: (text: string) => Promise<void>;
}) {
  return groupMessages(messages).map((group) => {
    const first = group[0];
    return isToolRun(group) ? (
      <article key={first.id} className="message message-assistant message-tool-activity">
        <div className="message-body">
          <ToolActivityGroup messages={group} tools={tools} approvals={approvals} />
        </div>
      </article>
    ) : (
      <MessageView
        onAction={onAction}
        key={first.id}
        message={first}
        tools={tools}
        login={login}
        approvals={approvals}
      />
    );
  });
}
