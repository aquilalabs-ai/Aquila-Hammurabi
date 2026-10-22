import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, X, FileText } from "lucide-react";
import { useIngestCorpus } from "../../api/hooks/useCorpus";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import { cn } from "../ui/cn";
import { Spinner } from "../ui/Spinner";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function CorpusIngestModal({ open, onClose }: Props) {
  const [name, setName] = useState("");
  const [jurisdiction, setJurisdiction] = useState("FR");
  const [file, setFile] = useState<File | null>(null);
  const ingest = useIngestCorpus();

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) setFile(accepted[0]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"], "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"] },
    multiple: false,
  });

  if (!open) return null;

  const handleSubmit = () => {
    if (!file || !name) return;
    const ext = file.name.split(".").pop()?.toLowerCase();
    const sourceType = ext === "docx" ? "docx" : "pdf";
    const fd = new FormData();
    fd.append("file", file);
    fd.append("name", name);
    fd.append("jurisdiction", jurisdiction);
    fd.append("source_type", sourceType);
    ingest.mutate(fd, { onSuccess: () => { onClose(); setFile(null); setName(""); } });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-800 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-700 px-5 py-4">
          <h2 className="text-sm font-semibold text-slate-100">Ingest Corpus</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 p-5">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">Corpus name</label>
            <Input
              placeholder="e.g. French Civil Code 2024"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">Jurisdiction</label>
            <Input
              placeholder="FR"
              value={jurisdiction}
              onChange={(e) => setJurisdiction(e.target.value)}
              className="uppercase"
              maxLength={5}
            />
          </div>

          <div
            {...getRootProps()}
            className={cn(
              "rounded-lg border-2 border-dashed p-6 text-center cursor-pointer transition-colors",
              isDragActive
                ? "border-gold-400 bg-gold-400/10"
                : "border-slate-600 hover:border-slate-500",
            )}
          >
            <input {...getInputProps()} />
            {file ? (
              <div className="flex items-center justify-center gap-2 text-slate-300">
                <FileText className="h-5 w-5 text-gold-400" />
                <span className="text-sm">{file.name}</span>
              </div>
            ) : (
              <div className="text-slate-500">
                <Upload className="mx-auto mb-2 h-8 w-8 text-slate-600" />
                <p className="text-sm">Drop PDF or DOCX here, or click to browse</p>
              </div>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-700 px-5 py-3">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleSubmit}
            disabled={!file || !name || ingest.isPending}
          >
            {ingest.isPending ? <Spinner className="h-3.5 w-3.5" /> : <Upload className="h-3.5 w-3.5" />}
            Ingest
          </Button>
        </div>
      </div>
    </div>
  );
}
