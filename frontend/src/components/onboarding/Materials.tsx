import { useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowUpFromLine, Check, FileText, Paperclip, X } from "lucide-react";
import { Button } from "../ui/button";
import { ACCEPTED_FILES, fileKey, formatSize, selectFiles } from "./model";

export function Materials({
  files,
  onChange,
  inputLabel = "Choose course materials",
}: {
  files: File[];
  onChange: (files: File[]) => void;
  inputLabel?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const [dragging, setDragging] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [announcement, setAnnouncement] = useState("");
  const reduced = useReducedMotion();
  function add(incoming: File[]) {
    const result = selectFiles(files, incoming);
    onChange(result.files);
    setErrors(result.errors);
    const count = result.files.length - files.length;
    setAnnouncement(
      `${count} ${count === 1 ? "file" : "files"} added. ${result.files.length} selected in this tab.`,
    );
  }
  return (
    <div>
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPTED_FILES}
        className="sr-only"
        tabIndex={-1}
        aria-label={inputLabel}
        onChange={(event) => {
          add(Array.from(event.target.files ?? []));
          event.target.value = "";
        }}
      />
      <div
        className={`material-dropzone ${dragging ? "is-dragging" : ""}`}
        onDragEnter={(event) => {
          event.preventDefault();
          dragDepth.current += 1;
          setDragging(true);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          event.dataTransfer.dropEffect = "copy";
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          dragDepth.current -= 1;
          if (dragDepth.current <= 0) {
            dragDepth.current = 0;
            setDragging(false);
          }
        }}
        onDrop={(event) => {
          event.preventDefault();
          dragDepth.current = 0;
          setDragging(false);
          add(Array.from(event.dataTransfer.files));
        }}
      >
        <span className="upload-symbol" aria-hidden="true">
          <ArrowUpFromLine size={23} strokeWidth={1.7} />
        </span>
        <div>
          <p className="font-heading text-base font-semibold text-foreground">
            {dragging ? "Drop them here." : "Keep course files together."}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Lecture notes, slides, homework, or past papers.
          </p>
        </div>
        <Button
          variant="secondary"
          className="mt-4 min-h-10 bg-surface px-4 py-2 text-sm"
          onClick={() => input.current?.click()}
        >
          <Paperclip size={15} />
          Choose files
        </Button>
        <p className="mt-3 text-xs text-muted-foreground">
          PDF, DOCX, PPTX, TXT, MD · 20 MB per file · up to 8 files
        </p>
      </div>
      {errors.length > 0 && (
        <div
          role="alert"
          className="mt-3 border-l-2 border-coral bg-coral/10 px-4 py-3 text-sm text-foreground"
        >
          <ul className="space-y-1">
            {errors.map((error, i) => (
              <li key={`${error}-${i}`}>{error}</li>
            ))}
          </ul>
        </div>
      )}
      {files.length > 0 && (
        <div className="mt-4">
          <div className="mb-1 flex justify-between text-xs text-muted-foreground">
            <span>
              {files.length} {files.length === 1 ? "file" : "files"} selected
            </span>
            <span>In this tab only</span>
          </div>
          <ul className="materials-list" aria-label="Selected course materials">
            <AnimatePresence initial={false}>
              {files.map((file) => (
                <motion.li
                  key={fileKey(file)}
                  layout={!reduced}
                  initial={{ opacity: reduced ? 1 : 0, y: reduced ? 0 : 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, height: reduced ? "auto" : 0 }}
                  transition={{ duration: reduced ? 0 : 0.18 }}
                  className="material-row"
                >
                  <span className="file-symbol">
                    <FileText size={19} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <span
                      className="block truncate text-sm font-medium"
                      title={file.name}
                    >
                      {file.name}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {formatSize(file.size)}
                    </span>
                  </div>
                  <span className="inline-flex items-center gap-1 text-xs text-teal-dark">
                    <Check size={14} />
                    Selected
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-11 shrink-0 text-muted-foreground hover:bg-coral/10 hover:text-foreground"
                    aria-label={`Remove ${file.name}`}
                    onClick={() => {
                      onChange(
                        files.filter(
                          (existing) => fileKey(existing) !== fileKey(file),
                        ),
                      );
                      setErrors([]);
                      setAnnouncement(`${file.name} removed.`);
                    }}
                  >
                    <X size={16} />
                  </Button>
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
        </div>
      )}
      <p className="mt-3 text-xs leading-5 text-muted-foreground">
        Files stay in this tab. They haven’t been uploaded or processed, and are
        not supplied to the tutor.
      </p>
      <span className="sr-only" role="status">
        {announcement}
      </span>
    </div>
  );
}
