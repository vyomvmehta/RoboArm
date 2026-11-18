import { ReactNode } from "react";

export interface CodeFile {
  label: string; // "ik()"
  path: string; // repo path
  lang: "python" | "cpp";
  code: string;
  firstLine: number;
}

const KW = {
  python: /\b(def|return|if|else|elif|not|and|or|raise|for|in|is|None|True|False|import|from|class)\b/,
  cpp: /\b(static|void|const|if|else|for|return|uint8_t|uint16_t|uint32_t|char|bool|true|false|switch|case|break)\b/,
};

function tokens(line: string, lang: "python" | "cpp"): ReactNode[] {
  const comment = lang === "python" ? "#" : "//";
  const re = new RegExp(
    `(${comment === "#" ? "#.*$" : "\\/\\/.*$"})|("(?:[^"\\\\]|\\\\.)*"|'(?:[^'\\\\]|\\\\.)*')|(${KW[lang].source})|(\\b\\d+(?:\\.\\d+)?(?:UL)?\\b)|(\\b[A-Za-z_]\\w*(?=\\())`,
    "g",
  );
  const out: ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(line))) {
    if (m.index > last) out.push(line.slice(last, m.index));
    const cls = m[1] ? "text-mute italic" : m[2] ? "text-emerald-300/90" : m[3] ? "text-signal" : m[4] ? "text-scope" : "text-paper";
    out.push(
      <span key={m.index} className={cls}>
        {m[0]}
      </span>,
    );
    last = m.index + m[0].length;
  }
  if (last < line.length) out.push(line.slice(last));
  return out;
}

/** Read-only code viewer. The text is cut from the real repo file at build time. */
export default function CodeView({ file, maxHeight = "22rem" }: { file: CodeFile; maxHeight?: string }) {
  const lines = file.code.split("\n");
  return (
    <div className="hairline bg-black/50">
      <div className="flex items-center justify-between border-b border-white/[0.08] px-3 py-2">
        <span className="font-mono text-[11px] text-paper/80">{file.path}</span>
        <span className="label">
          L{file.firstLine}-{file.firstLine + lines.length - 1}
        </span>
      </div>
      <pre className="overflow-auto py-3 font-mono text-[11.5px] leading-[1.65]" style={{ maxHeight }} tabIndex={0}>
        {lines.map((l, i) => (
          <div key={i} className="flex px-3 hover:bg-white/[0.03]">
            <span className="mr-4 w-8 shrink-0 select-none text-right text-white/25">{file.firstLine + i}</span>
            <code className="whitespace-pre text-paper/75">{tokens(l, file.lang)}</code>
          </div>
        ))}
      </pre>
    </div>
  );
}
