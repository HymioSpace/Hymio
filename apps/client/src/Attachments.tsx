import { useEffect, useRef, useState, type RefObject } from 'react';
import { Plus, X, LoaderCircle, FileText, Music2 } from 'lucide-react';
import type { LoginState } from './useLogin';

export interface Attachment {
  attachment_id: string;
  name: string;
  mime: string;
  url: string;
  size: number;
  preview?: string;
}
export function attachmentText(files: Attachment[]) {
  return files
    .map(
      (file) =>
        `${file.mime.startsWith('image/') ? '!' : ''}[${file.name.replace(/[\[\]\\]/g, '')}](${file.url})`,
    )
    .join('\n');
}
export function Attachments({
  login,
  files,
  onChange,
  onBusy,
  onError,
  pasteTarget,
}: {
  login: LoginState;
  files: Attachment[];
  onChange: (files: Attachment[]) => void;
  onBusy: (busy: boolean) => void;
  onError: (error: string) => void;
  pasteTarget: RefObject<HTMLTextAreaElement | null>;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const active = useRef(true);
  const busy = useRef(false);
  const uploadCurrent = useRef<(files: File[]) => void>(() => {});
  const previews = useRef<Attachment[]>([]);
  useEffect(() => {
    for (const file of previews.current) {
      if (file.preview && !files.some((item) => item.preview === file.preview))
        URL.revokeObjectURL(file.preview);
    }
    previews.current = files;
  }, [files]);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
      for (const file of previews.current) if (file.preview) URL.revokeObjectURL(file.preview);
    };
  }, []);
  useEffect(() => {
    const target = pasteTarget.current;
    if (!target) return;
    const paste = (event: ClipboardEvent) => {
      const images = Array.from(event.clipboardData?.items || [])
        .filter((item) => item.kind === 'file' && item.type.startsWith('image/'))
        .map((item) => item.getAsFile())
        .filter((file): file is File => file !== null);
      if (!images.length) return;
      event.preventDefault();
      uploadCurrent.current(
        images.map(
          (file, index) =>
            new File(
              [file],
              `screenshot-${Date.now()}-${index + 1}.${file.type === 'image/jpeg' ? 'jpg' : file.type === 'image/webp' ? 'webp' : 'png'}`,
              { type: file.type },
            ),
        ),
      );
    };
    target.addEventListener('paste', paste);
    return () => target.removeEventListener('paste', paste);
  }, [pasteTarget]);
  async function upload(selected: FileList | File[] | null) {
    if (!selected || !login.session) return;
    if (busy.current) {
      onError('附件正在上传，完成后可继续粘贴');
      return;
    }
    if (selected.length + files.length > 8) {
      onError('每条消息最多添加 8 个附件');
      return;
    }
    busy.current = true;
    setUploading(true);
    onBusy(true);
    const next = [...files];
    try {
      for (const file of Array.from(selected)) {
        if (file.size > 20 * 1024 * 1024) throw new Error('单个文件不能超过 20 MB');
        const response = await fetch(login.session.backend + '/attachments', {
          method: 'POST',
          headers: {
            Authorization: 'Bearer ' + login.session.access_token,
            'X-File-Name': encodeURIComponent(file.name),
          },
          body: file,
          signal: AbortSignal.timeout(60000),
          redirect: 'error',
        });
        if (!response.ok)
          throw new Error(response.status === 415 ? '暂不支持此文件格式' : '附件上传失败，请重试');
        const attachment: Attachment = await response.json();
        if (file.type.startsWith('image/')) attachment.preview = URL.createObjectURL(file);
        if (!active.current) {
          if (attachment.preview) URL.revokeObjectURL(attachment.preview);
          return;
        }
        next.push(attachment);
        if (active.current) onChange([...next]);
      }
    } catch (error) {
      if (active.current) onError(error instanceof Error ? error.message : '上传失败');
    } finally {
      busy.current = false;
      if (active.current) {
        setUploading(false);
        onBusy(false);
      }
      if (input.current) input.current.value = '';
    }
  }
  uploadCurrent.current = (files) => {
    void upload(files);
  };
  return (
    <div className="attachment-control" onClick={(event) => event.stopPropagation()}>
      <input
        ref={input}
        type="file"
        multiple
        hidden
        accept="image/*,.mp3,.wav,.m4a,.ogg,.flac,.pdf,.docx,.pptx,.xlsx,.xls,.csv,.txt,.md,.html,.json,.xml,.yaml,.yml"
        onChange={(event) => void upload(event.target.files)}
      />
      <button
        className="attachment-add"
        type="button"
        disabled={uploading || files.length >= 8}
        onClick={() => input.current?.click()}
        aria-label="添加图片或文件"
        title="添加图片、文件或音频"
      >
        {uploading ? (
          <LoaderCircle size={17} className="spin" />
        ) : (
          <Plus size={20} strokeWidth={1.7} />
        )}
      </button>
      {(files.length > 0 || uploading) && (
        <div className="attachment-tray" aria-label="已添加附件">
          {files.map((file) => (
            <span className="attachment-chip" key={file.attachment_id}>
              {file.preview ? (
                <img src={file.preview} alt="" className="attachment-thumbnail" />
              ) : (
                <span className="attachment-file-icon">
                  {file.mime.startsWith('audio/') ? <Music2 size={20} /> : <FileText size={20} />}
                </span>
              )}
              <span className="attachment-file-copy">
                <strong>{file.name}</strong>
                <small>
                  {file.mime.startsWith('image/')
                    ? '图片'
                    : file.mime.startsWith('audio/')
                      ? '音频'
                      : file.name.split('.').pop()?.toUpperCase()}{' '}
                  ·{' '}
                  {file.size < 1024 * 1024
                    ? Math.max(1, Math.round(file.size / 1024)) + ' KB'
                    : (file.size / (1024 * 1024)).toFixed(1) + ' MB'}
                </small>
              </span>
              <button
                aria-label={'移除 ' + file.name}
                disabled={uploading}
                onClick={() => onChange(files.filter((item) => item !== file))}
              >
                <X size={13} />
              </button>
            </span>
          ))}
          {uploading && (
            <span className="attachment-upload-state">
              <LoaderCircle size={16} className="spin" />
              正在添加附件…
            </span>
          )}
        </div>
      )}
    </div>
  );
}
