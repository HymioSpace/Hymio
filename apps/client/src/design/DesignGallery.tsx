import { ConnectionsPanel } from '../ConnectionsPanel';
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Button, Companion, IconButton, Sheet, StatusBadge, type Mood } from '@hymio/ui';
import type { Approval } from '@hymio/client';
import { ApprovalCard } from '../ApprovalCard';
import '../styles.css';
import './gallery.css';
import { ToolActivityGroup } from '../ToolActivityGroup';
function Gallery() {
  const [sheet, setSheet] = useState(false);
  const approval: Approval = {
    id: 'design-approval',
    tool: 'bash',
    arguments: { command: 'pnpm test', description: '运行测试' },
    status: 'pending',
    expiresAt: Math.ceil(Date.now() / 1000) + 300,
    title: '运行测试',
    summary: '读取当前项目并运行测试。',
    risk: 'medium',
    effects: ['execute', 'local_access'],
    target: { kind: 'device', id: 'mac-mini', label: 'Mac mini' },
    scopeOptions: ['once', 'run'],
    actionDigest: '0'.repeat(64),
    grantKey: 'synthetic-grant',
  };
  return (
    <main className="studio">
      <header>
        <b>
          hymio<span>Design notes / 01</span>
        </b>
        <span>A little more in tune.</span>
      </header>
      <section className="intro">
        <div>
          <p className="eyebrow">THE EVERYDAY COMPANION</p>
          <h1>
            有自己的节奏。
            <br />
            也和你同频。
          </h1>
          <p>
            让工具退后一步，让对话和陪伴更近一点。
            <br />
            一条持续的对话，在不同设备上自然继续。
          </p>
        </div>
        <div className="hero-character">
          <Companion />
          <span>小小的水獭，蓝色的围巾。轻轻陪着，认真做事。</span>
        </div>
      </section>
      <section>
        <h2>01 / 一点性格，五种状态</h2>
        <div className="moods">
          {(['idle', 'working', 'replying', 'waiting', 'offline'] as Mood[]).map((m, i) => (
            <article key={m}>
              <Companion mood={m} />
              <strong>{['在这里', '认真想想', '有话想说', '等你点头', '暂时离线'][i]}</strong>
              <small>{m}</small>
            </article>
          ))}
        </div>
      </section>
      <section>
        <h2>02 / 把注意力留给内容</h2>
        <div className="screens">
          <article className="desktop-sketch">
            <nav>
              <b>h</b>
              <span>◌</span>
            </nav>
            <div className="sketch-body">
              <div className="sketch-header">
                <b>hymio</b>
                <StatusBadge tone="active">随时在这里</StatusBadge>
              </div>
              <div className="sample-thread">
                <p className="user">帮我把今天的想法理一理。</p>
                <div className="assistant">
                  <Companion compact />
                  <div>
                    <p>当然，我们从最重要的一件事开始。</p>
                    <p className="secondary">今天有什么是你最想推进的？</p>
                    <details>
                      <summary>✓ 已完成 2 项操作</summary>
                      <p>查看日程 · 整理安排</p>
                    </details>
                  </div>
                </div>
              </div>
              <div className="sketch-composer">
                <textarea aria-label="设计稿输入框" placeholder="想到什么，就和我说说…" />
                <Button variant="primary">↑</Button>
              </div>
              <small className="secondary">同一段对话，随时继续。</small>
            </div>
          </article>
          <article className="phone-sketch">
            <div className="phone-time">
              9:41 <span>● ▰</span>
            </div>
            <b>hymio</b>
            <div className="phone-welcome">
              <Companion />
              <h3>嗨，我在。</h3>
              <p>想到什么，就和我说说。</p>
            </div>
            <div className="phone-input">
              接着说，我在听… <span>↑</span>
            </div>
          </article>
        </div>
      </section>
      <section>
        <h2>03 / 小而完整的组件</h2>
        <div className="primitives">
          <Button variant="primary">发送消息</Button>
          <Button>查看设备</Button>
          <Button variant="quiet">取消</Button>
          <Button variant="danger">解除绑定</Button>
          <Button busy>正在连接</Button>
          <Button disabled>不可用</Button>
          <IconButton label="打开详情" onClick={() => setSheet(true)}>
            ↗
          </IconButton>
          <StatusBadge tone="active">已连接</StatusBadge>
          <StatusBadge tone="attention">需要确认</StatusBadge>
        </div>
        <div className="swatches">
          {['surface', 'ink', 'muted', 'blue', 'line', 'pale'].map((t) => (
            <div key={t}>
              <i style={{ background: `var(--${t})` }} />
              <code>{t}</code>
            </div>
          ))}
        </div>
      </section>
      <section>
        <h2>04 / 真正的工具组件 · 合成状态示例</h2>
        <div className="tool-samples">
          {['running', 'awaiting_approval', 'succeeded', 'failed'].map((state, i) => (
            <ToolActivityGroup
              key={state}
              messages={[
                {
                  id: `example-${i}`,
                  stepId: `example-${i}`,
                  role: 'assistant',
                  content: '',
                  time: '',
                  calls: [
                    {
                      name: 'browser',
                      arguments: { action: 'navigate', url: 'https://example.com' },
                    },
                  ],
                },
              ]}
              tools={
                state === 'awaiting_approval'
                  ? []
                  : [
                      {
                        id: `example-${i}-0`,
                        tool: 'browser',
                        outcome: state,
                        result: '合成示例结果',
                        time: '',
                      },
                    ]
              }
              approvals={
                state === 'awaiting_approval'
                  ? [
                      {
                        id: `example-${i}-0`,
                        tool: 'browser',
                        arguments: {},
                        status: 'pending',
                        expiresAt: 4102444800,
                        title: '允许操作浏览器页面？',
                        summary: 'Hymio 将填写并提交当前页面。',
                        risk: 'high',
                        effects: ['browser_control'],
                        target: { kind: 'origin', id: 'example.com', label: 'example.com' },
                        scopeOptions: ['once', 'run'],
                        actionDigest: '0'.repeat(64),
                        grantKey: 'synthetic-grant',
                      },
                    ]
                  : []
              }
            />
          ))}
        </div>
        <article className="approval-sample">
          <p>我已检查项目结构，准备运行测试。</p>
          <ApprovalCard
            approval={approval}
            connected
            pending={false}
            clock={Date.now()}
            onDecide={async () => {}}
          />
        </article>
      </section>
      <footer>布局草图与组件预览 · 内容为合成示例 · 不连接 Agent 或账号服务</footer>
      {sheet && (
        <Sheet labelledBy="sample-title" onClose={() => setSheet(false)}>
          <h2 id="sample-title">一件小事，清楚地完成。</h2>
          <p>组件负责焦点、键盘和布局。业务决定内容和操作。</p>
          <Button onClick={() => setSheet(false)}>完成</Button>
        </Sheet>
      )}
    </main>
  );
}
createRoot(document.getElementById('root')!).render(
  new URLSearchParams(location.search).has('connectors') ? (
    <main
      style={{
        maxWidth: 1120,
        margin: '40px auto',
        padding: 32,
        background: 'white',
        borderRadius: 28,
      }}
    >
      <ConnectionsPanel preview onBack={() => {}} />
    </main>
  ) : (
    <Gallery />
  ),
);
