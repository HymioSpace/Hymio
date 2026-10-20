import io
import multiprocessing
import zipfile

DOCUMENTS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".xls",
    ".csv",
    ".html",
    ".htm",
    ".txt",
    ".md",
    ".json",
    ".xml",
    ".log",
    ".yaml",
    ".yml",
}


def _convert(content, suffix, sender):
    try:
        from markitdown import MarkItDown, StreamInfo

        result = MarkItDown(enable_plugins=False).convert_stream(
            io.BytesIO(content), stream_info=StreamInfo(extension=suffix)
        )
        sender.send({"markdown": result.text_content[:160000]})
    except Exception:
        sender.send({"error": "Document conversion failed or format unsupported"})
    finally:
        sender.close()


def to_markdown(content, suffix):
    if suffix not in DOCUMENTS:
        raise ValueError("Unsupported document format")
    if content.startswith(b"PK"):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if (
                len(archive.infolist()) > 5000
                or sum(i.file_size for i in archive.infolist()) > 80_000_000
            ):
                raise ValueError("Document archive is too large")
    ctx = multiprocessing.get_context("spawn")
    receiver, sender = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_convert, args=(content, suffix, sender), daemon=True)
    process.start()
    sender.close()
    try:
        if not receiver.poll(30):
            raise ValueError("Document conversion timed out")
        result = receiver.recv()
        if "error" in result:
            raise ValueError(result["error"])
        return result["markdown"]
    finally:
        if process.is_alive():
            process.terminate()
        process.join(2)
        receiver.close()
