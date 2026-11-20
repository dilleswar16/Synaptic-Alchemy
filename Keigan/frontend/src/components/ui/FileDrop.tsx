import { useId, useRef, useState, type DragEvent, type ReactNode } from "react";
import { CircleCheck, CircleExclamationPoint, FileText, UploadCloud, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";
import { formatFileSize, formatPercentage } from "@/utils/formatters";
import { ProgressBar } from "./ProgressBar";

export interface FileDropItem {
  key: string;
  fileName: string;
  fileSizeBytes?: number;
  /** 0–100 while uploading. */
  progressPercentage?: number;
  status: "pending" | "uploading" | "done" | "error";
  errorMessage?: ReactNode;
}

export interface FileRejection {
  file: File;
  reason: "type" | "size";
}

export interface FileDropProps {
  /** Extensions and/or MIME types: [".md", ".pdf", "image/png"]. Empty = any. */
  acceptedFileTypes?: string[];
  /** Human list shown to the user ("Markdown, PDF, PNG, JPG, SVG"); defaults to the raw types. */
  acceptedTypesLabel?: string;
  maximumFileSizeBytes?: number;
  isMultiple?: boolean;
  onFilesSelected: (files: File[]) => void;
  onFilesRejected?: (rejections: FileRejection[]) => void;
  /** Per-file progress rows rendered under the drop zone. */
  items?: FileDropItem[];
  onRemoveItem?: (itemKey: string) => void;
  disabled?: boolean;
  className?: string;
}

function isFileTypeAccepted(file: File, acceptedFileTypes: string[]): boolean {
  if (acceptedFileTypes.length === 0) {
    return true;
  }
  const lowerCaseName = file.name.toLowerCase();
  return acceptedFileTypes.some((acceptedType) => {
    const normalisedType = acceptedType.toLowerCase();
    if (normalisedType.startsWith(".")) {
      return lowerCaseName.endsWith(normalisedType);
    }
    if (normalisedType.endsWith("/*")) {
      return file.type.startsWith(normalisedType.slice(0, -1));
    }
    return file.type === normalisedType;
  });
}

/** Dashed drop zone with keyboard-accessible browse, type/size validation and per-file progress rows. */
export function FileDrop({
  acceptedFileTypes = [],
  acceptedTypesLabel,
  maximumFileSizeBytes,
  isMultiple = true,
  onFilesSelected,
  onFilesRejected,
  items = [],
  onRemoveItem,
  disabled = false,
  className,
}: FileDropProps) {
  const { t } = useTranslation("common");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const [isDragOver, setIsDragOver] = useState(false);
  const [rejections, setRejections] = useState<FileRejection[]>([]);

  const handleFiles = (fileList: FileList | null) => {
    if (!fileList || disabled) {
      return;
    }
    const candidateFiles = Array.from(fileList).slice(0, isMultiple ? undefined : 1);
    const acceptedFiles: File[] = [];
    const rejectedFiles: FileRejection[] = [];
    for (const file of candidateFiles) {
      if (!isFileTypeAccepted(file, acceptedFileTypes)) {
        rejectedFiles.push({ file, reason: "type" });
      } else if (maximumFileSizeBytes !== undefined && file.size > maximumFileSizeBytes) {
        rejectedFiles.push({ file, reason: "size" });
      } else {
        acceptedFiles.push(file);
      }
    }
    setRejections(rejectedFiles);
    if (rejectedFiles.length > 0) {
      onFilesRejected?.(rejectedFiles);
    }
    if (acceptedFiles.length > 0) {
      onFilesSelected(acceptedFiles);
    }
  };

  const handleDrop = (dragEvent: DragEvent<HTMLLabelElement>) => {
    dragEvent.preventDefault();
    setIsDragOver(false);
    handleFiles(dragEvent.dataTransfer.files);
  };

  const typesText = acceptedTypesLabel ?? acceptedFileTypes.join(", ");
  const sizeText = maximumFileSizeBytes ? formatFileSize(maximumFileSizeBytes) : null;

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <label
        htmlFor={inputId}
        onDragOver={(dragEvent) => {
          dragEvent.preventDefault();
          if (!disabled) {
            setIsDragOver(true);
          }
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed border-strong bg-surface px-6 py-8 text-center transition-colors",
          "hover:border-action/60 hover:bg-surface-hover has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-focus has-[:focus-visible]:outline-offset-1",
          isDragOver && "border-action bg-action-subtle",
          disabled && "pointer-events-none opacity-50",
        )}
      >
        <span aria-hidden="true" className="grid size-11 place-items-center rounded-full bg-gradient-brand-soft text-action">
          <UploadCloud size={22} strokeWidth={1.75} />
        </span>
        <span className="text-body text-default">
          {isDragOver ? (
            t("fileDrop.dropToUpload")
          ) : (
            <>
              {t("fileDrop.dropFiles")} <span className="font-semibold text-action underline-offset-2 hover:underline">{t("fileDrop.browse")}</span>
            </>
          )}
        </span>
        {typesText || sizeText ? (
          <span className="text-caption text-muted">
            {[typesText ? t("fileDrop.acceptedTypes", { types: typesText }) : null, sizeText ? t("fileDrop.maximumSize", { size: sizeText }) : null]
              .filter(Boolean)
              .join(" · ")}
          </span>
        ) : null}
        <input
          ref={fileInputRef}
          id={inputId}
          type="file"
          className="sr-only"
          multiple={isMultiple}
          accept={acceptedFileTypes.join(",") || undefined}
          disabled={disabled}
          onChange={(changeEvent) => {
            handleFiles(changeEvent.target.files);
            changeEvent.target.value = "";
          }}
        />
      </label>

      {rejections.length > 0 ? (
        <ul role="alert" className="flex flex-col gap-1">
          {rejections.map((rejection) => (
            <li key={`${rejection.file.name}-${rejection.reason}`} className="flex items-start gap-1.5 text-caption text-danger">
              <CircleExclamationPoint aria-hidden="true" size={14} className="mt-0.5 shrink-0" />
              {rejection.reason === "type"
                ? t("fileDrop.rejectedType", { fileName: rejection.file.name })
                : t("fileDrop.rejectedSize", { fileName: rejection.file.name, size: sizeText ?? "" })}
            </li>
          ))}
        </ul>
      ) : null}

      {items.length > 0 ? (
        <ul className="flex flex-col divide-y divide-hairline rounded-md border border-hairline bg-surface">
          {items.map((item) => (
            <li key={item.key} className="flex items-center gap-3 px-4 py-3">
              <FileText aria-hidden="true" size={20} strokeWidth={1.75} className="shrink-0 text-muted" />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="truncate text-body-sm font-medium text-default">{item.fileName}</span>
                  <span className="shrink-0 text-caption text-muted tabular-numbers">
                    {item.status === "uploading"
                      ? t("fileDrop.uploading", { percentage: formatPercentage(item.progressPercentage ?? 0, { maximumFractionDigits: 0 }) })
                      : item.status === "done"
                        ? t("fileDrop.uploaded")
                        : item.status === "error"
                          ? t("fileDrop.failed")
                          : item.fileSizeBytes !== undefined
                            ? formatFileSize(item.fileSizeBytes)
                            : t("fileDrop.pending")}
                  </span>
                </div>
                {item.status === "uploading" ? <ProgressBar value={item.progressPercentage ?? 0} size="xs" className="mt-1.5" /> : null}
                {item.status === "error" && item.errorMessage ? <p className="mt-0.5 text-caption text-danger">{item.errorMessage}</p> : null}
              </div>
              {item.status === "done" ? <CircleCheck aria-hidden="true" size={18} strokeWidth={2} className="shrink-0 text-success" /> : null}
              {item.status === "error" ? <CircleExclamationPoint aria-hidden="true" size={18} strokeWidth={2} className="shrink-0 text-danger" /> : null}
              {onRemoveItem ? (
                <button
                  type="button"
                  aria-label={t("fileDrop.removeFile", { fileName: item.fileName })}
                  onClick={() => onRemoveItem(item.key)}
                  className="grid size-7 shrink-0 place-items-center rounded-sm text-muted hover:bg-surface-hover hover:text-default"
                >
                  <X aria-hidden="true" size={16} />
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
