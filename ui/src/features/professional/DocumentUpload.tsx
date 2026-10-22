import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, FileText, X, Loader2 } from "lucide-react";
import { useUploadDocument, useTriggerAnalysis } from "../../api/hooks/useDocuments";
import { useAppStore } from "../../store/app";
import { Button } from "../../components/ui/Button";
import { cn } from "../../components/ui/cn";

export function DocumentUpload({ onUploaded }: { onUploaded?: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const { activeCorpusId, setActiveDocument } = useAppStore();
  const upload = useUploadDocument();
  const analyze = useTriggerAnalysis();

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) setFile(accepted[0]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    },
    multiple: false,
  });

  const handleUpload = () => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    if (activeCorpusId) fd.append("corpus_id", activeCorpusId);

    upload.mutate(fd, {
      onSuccess: (doc) => {
        setActiveDocument(doc.id);
        setFile(null);
        analyze.mutate(
          { docId: doc.id },
          { onError: (err) => setAnalyzeError((err as Error).message) },
        );
        onUploaded?.();
      },
    });
  };

  return (
    <div className="space-y-3">
      <div
        {...getRootProps()}
        className={cn(
          "flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center cursor-pointer transition-colors",
          isDragActive
            ? "border-gold-400 bg-gold-400/10"
            : "border-slate-600 bg-slate-800/40 hover:border-slate-500",
        )}
      >
        <input {...getInputProps()} />
        {file ? (
          <div className="flex items-center gap-3">
            <FileText className="h-8 w-8 text-gold-400" />
            <div className="text-left">
              <p className="text-sm font-medium text-slate-200">{file.name}</p>
              <p className="text-xs text-slate-500">{(file.size / 1024).toFixed(1)} KB</p>
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); setFile(null); }}
              className="ml-2 text-slate-500 hover:text-slate-300"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <>
            <Upload className="mb-3 h-10 w-10 text-slate-600" />
            <p className="text-sm text-slate-400">
              Drag & drop a <span className="text-gold-400">PDF</span> or{" "}
              <span className="text-gold-400">DOCX</span> contract
            </p>
            <p className="mt-1 text-xs text-slate-600">or click to browse</p>
          </>
        )}
      </div>

      {file && (
        <Button
          variant="primary"
          className="w-full"
          onClick={handleUpload}
          disabled={upload.isPending}
        >
          {upload.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Upload className="h-4 w-4" />
          )}
          Upload &amp; Analyse
        </Button>
      )}

      {upload.isError && (
        <p className="text-xs text-red-400">{(upload.error as Error).message}</p>
      )}
      {analyzeError && (
        <p className="text-xs text-red-400">Analysis failed: {analyzeError}</p>
      )}
    </div>
  );
}
