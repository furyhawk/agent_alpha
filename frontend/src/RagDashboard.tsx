import { useState, useEffect, useRef } from "react";
import {
  listRagCollections,
  getRagCollectionInfo,
  deleteRagCollection,
  listRagDocuments,
  deleteRagDocument,
  retryRagDocument,
  uploadRagDocument,
  listRagSyncLogs,
  type RAGCollectionInfo,
  type RAGTrackedDocument,
  type RAGSyncLog,
} from "./api";

/* ──────────────────────────────────────────────────────────────────────── */
/*  Props                                                                   */
/* ──────────────────────────────────────────────────────────────────────── */

interface RagProps {
  onBack: () => void;
}

const STATUS_COLORS: Record<string, string> = {
  done: "bg-emerald-900/50 text-emerald-400",
  processing: "bg-amber-900/50 text-amber-400",
  error: "bg-red-900/50 text-red-400",
  running: "bg-blue-900/50 text-blue-400",
  cancelled: "bg-gray-800 text-gray-400",
  partial: "bg-amber-900/50 text-amber-400",
};

function statusBadge(status: string) {
  const c = STATUS_COLORS[status] ?? "bg-gray-800 text-gray-400";
  return `rounded-full px-2.5 py-0.5 text-xs font-medium ${c}`;
}

function formatSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

/* ──────────────────────────────────────────────────────────────────────── */
/*  Main Dashboard                                                          */
/* ──────────────────────────────────────────────────────────────────────── */

export default function RagDashboard({ onBack }: RagProps) {
  const [tab, setTab] = useState<"overview" | "documents" | "collections">("overview");

  const [collections, setCollections] = useState<string[]>([]);
  const [collectionsInfo, setCollectionsInfo] = useState<Map<string, RAGCollectionInfo>>(new Map());
  const [documents, setDocuments] = useState<RAGTrackedDocument[]>([]);
  const [syncLogs, setSyncLogs] = useState<RAGSyncLog[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  /* ── Load all data ───────────────────────────────────────────────────── */

  const loadAll = async () => {
    setBusy(true);
    setError("");
    try {
      const [colNames, docs, logs] = await Promise.all([
        listRagCollections(),
        listRagDocuments(),
        listRagSyncLogs(),
      ]);
      setCollections(colNames);
      setDocuments(docs.items);
      setSyncLogs(logs.items);

      // Fetch info for each collection
      const infoMap = new Map<string, RAGCollectionInfo>();
      await Promise.all(
        colNames.map(async (name) => {
          try {
            infoMap.set(name, await getRagCollectionInfo(name));
          } catch {
            /* skip */
          }
        }),
      );
      setCollectionsInfo(infoMap);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load RAG data");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  /* ── Derived stats ──────────────────────────────────────────────────── */

  const totalVectors = Array.from(collectionsInfo.values()).reduce(
    (sum, c) => sum + c.total_vectors,
    0,
  );
  const totalDocuments = documents.length;
  const doneDocuments = documents.filter((d) => d.status === "done").length;
  const errorDocuments = documents.filter((d) => d.status === "error").length;

  /* ── Handlers ───────────────────────────────────────────────────────── */

  const handleDeleteCollection = async (name: string) => {
    if (!confirm(`Delete collection "${name}" and all its data?`)) return;
    try {
      await deleteRagCollection(name);
      await loadAll();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const handleDeleteDocument = async (docId: string) => {
    if (!confirm("Delete this document and all its vectors?")) return;
    try {
      await deleteRagDocument(docId);
      await loadAll();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const handleRetryDocument = async (docId: string) => {
    try {
      await retryRagDocument(docId);
      await loadAll();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Retry failed");
    }
  };

  /* ── Render ─────────────────────────────────────────────────────────── */

  return (
    <div className="mx-auto flex h-dvh max-w-6xl flex-col">
      {/* Header */}
      <header className="flex items-center gap-3 border-b border-gray-800 px-6 py-4">
        <button
          onClick={onBack}
          className="rounded-lg border border-gray-700 p-2 text-gray-400 transition hover:border-indigo-500 hover:text-indigo-400"
          title="Back to chat"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-600 to-teal-500 text-sm font-bold text-white shadow-lg shadow-emerald-500/25">
          R
        </div>
        <div className="flex-1">
          <h1 className="text-lg font-semibold leading-tight tracking-tight">
            RAG Dashboard
          </h1>
          <p className="text-xs text-gray-500">
            {totalVectors.toLocaleString()} vectors · {totalDocuments} documents
          </p>
        </div>

        <button
          onClick={loadAll}
          disabled={busy}
          className="rounded-lg border border-gray-700 px-3 py-1.5 text-sm text-gray-400 transition hover:border-indigo-500 hover:text-indigo-400 disabled:opacity-40"
        >
          Refresh
        </button>
      </header>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-800 px-6 pt-3">
        {(["overview", "documents", "collections"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-t-lg px-4 py-2 text-sm font-medium capitalize transition ${
              tab === t
                ? "border border-b-0 border-gray-700 bg-gray-900 text-gray-100"
                : "text-gray-500 hover:text-gray-300"
            }`}
          >
            {t}
            {t === "documents" && (
              <span className="ml-1.5 rounded-full bg-gray-800 px-1.5 py-0.5 text-xs">
                {totalDocuments}
              </span>
            )}
            {t === "collections" && (
              <span className="ml-1.5 rounded-full bg-gray-800 px-1.5 py-0.5 text-xs">
                {collections.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {error && (
          <div className="mb-4 rounded-lg bg-red-900/40 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}

        {busy && tab === "overview" ? (
          <div className="flex items-center justify-center py-20">
            <p className="text-sm text-gray-500">Loading…</p>
          </div>
        ) : tab === "overview" ? (
          <OverviewTab
            collections={collections}
            collectionsInfo={collectionsInfo}
            totalDocuments={totalDocuments}
            doneDocuments={doneDocuments}
            errorDocuments={errorDocuments}
            syncLogs={syncLogs}
          />
        ) : tab === "documents" ? (
          <DocumentsTab
            documents={documents}
            onDelete={handleDeleteDocument}
            onRetry={handleRetryDocument}
            onUpload={loadAll}
          />
        ) : (
          <CollectionsTab
            collections={collections}
            collectionsInfo={collectionsInfo}
            onDelete={handleDeleteCollection}
          />
        )}
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────── */
/*  Overview Tab                                                            */
/* ──────────────────────────────────────────────────────────────────────── */

function OverviewTab({
  collections,
  collectionsInfo,
  totalDocuments,
  doneDocuments,
  errorDocuments,
  syncLogs,
}: {
  collections: string[];
  collectionsInfo: Map<string, RAGCollectionInfo>;
  totalDocuments: number;
  doneDocuments: number;
  errorDocuments: number;
  syncLogs: RAGSyncLog[];
}) {
  const totalVectors = Array.from(collectionsInfo.values()).reduce(
    (sum, c) => sum + c.total_vectors,
    0,
  );
  const latestSync = syncLogs[0] ?? null;

  const cards = [
    {
      label: "Collections",
      value: collections.length,
      color: "from-emerald-500 to-teal-600",
    },
    {
      label: "Total Vectors",
      value: totalVectors.toLocaleString(),
      color: "from-indigo-500 to-purple-600",
    },
    {
      label: "Documents",
      value: totalDocuments,
      color: "from-amber-500 to-orange-600",
    },
    {
      label: "Ingested",
      value: doneDocuments,
      color: "from-emerald-500 to-teal-600",
    },
  ];

  return (
    <div className="space-y-8">
      {/* Stat cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
          <div
            key={card.label}
            className="rounded-xl border border-gray-800 bg-gray-900/60 p-5"
          >
            <p className="text-sm text-gray-500">{card.label}</p>
            <p className="mt-1 text-3xl font-bold text-gray-100">
              {card.value}
            </p>
            <div
              className={`mt-3 h-1 w-full rounded-full bg-gradient-to-r ${card.color}`}
            />
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Document status breakdown */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
          <h3 className="mb-3 text-sm font-semibold text-gray-300">
            Document Status
          </h3>
          <div className="space-y-2">
            {[
              { label: "Done", count: doneDocuments, color: "from-emerald-500 to-teal-500" },
              { label: "Error", count: errorDocuments, color: "from-red-500 to-rose-500" },
              { label: "Processing", count: totalDocuments - doneDocuments - errorDocuments, color: "from-amber-500 to-orange-500" },
            ].map(({ label, count, color }) => (
              <div key={label} className="flex items-center gap-3">
                <span className="w-24 text-sm text-gray-400">{label}</span>
                <div className="flex-1">
                  <div className="h-2 rounded-full bg-gray-800">
                    <div
                      className={`h-2 rounded-full bg-gradient-to-r ${color}`}
                      style={{
                        width: `${totalDocuments > 0 ? (count / totalDocuments) * 100 : 0}%`,
                      }}
                    />
                  </div>
                </div>
                <span className="w-8 text-right text-sm text-gray-400">
                  {count}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Collection details */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
          <h3 className="mb-3 text-sm font-semibold text-gray-300">
            Collections
          </h3>
          {collections.length === 0 ? (
            <p className="py-4 text-center text-sm text-gray-500">
              No collections yet.
            </p>
          ) : (
            <div className="space-y-3">
              {collections.slice(0, 10).map((name) => {
                const info = collectionsInfo.get(name);
                return (
                  <div
                    key={name}
                    className="flex items-center justify-between rounded-lg bg-gray-800/50 px-3 py-2"
                  >
                    <div>
                      <p className="text-sm text-gray-200">{name}</p>
                      {info && (
                        <p className="text-xs text-gray-500">
                          {info.total_vectors.toLocaleString()} vectors · {info.dim} dims
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Latest sync */}
      {latestSync && (
        <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
          <h3 className="mb-3 text-sm font-semibold text-gray-300">
            Latest Sync
          </h3>
          <div className="space-y-1 text-sm">
            <p className="text-gray-400">
              Collection:{" "}
              <span className="text-gray-200">{latestSync.collection_name}</span>
            </p>
            <p className="text-gray-400">
              Status:{" "}
              <span className={statusBadge(latestSync.status)}>
                {latestSync.status}
              </span>
            </p>
            <p className="text-gray-400">
              Files:{" "}
              <span className="text-gray-200">
                {latestSync.ingested} ingested · {latestSync.failed} failed ·{" "}
                {latestSync.skipped} skipped
              </span>
            </p>
            {latestSync.error_message && (
              <p className="text-red-400">Error: {latestSync.error_message}</p>
            )}
            {latestSync.completed_at && (
              <p className="text-xs text-gray-500">
                Completed: {new Date(latestSync.completed_at).toLocaleString()}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────── */
/*  Documents Tab                                                           */
/* ──────────────────────────────────────────────────────────────────────── */

function DocumentsTab({
  documents,
  onDelete,
  onRetry,
  onUpload,
}: {
  documents: RAGTrackedDocument[];
  onDelete: (id: string) => void;
  onRetry: (id: string) => void;
  onUpload: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [collectionFilter, setCollectionFilter] = useState("");

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadBusy(true);
    setUploadError("");
    try {
      const result = await uploadRagDocument(file, collectionFilter || undefined);
      alert(`Uploaded: ${result.filename} (${result.status})`);
      onUpload();
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploadBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const filtered = collectionFilter
    ? documents.filter((d) => d.collection_name === collectionFilter)
    : documents;

  const collections = [...new Set(documents.map((d) => d.collection_name))];

  return (
    <div className="space-y-6">
      {/* Upload section */}
      <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
        <h3 className="mb-3 text-sm font-semibold text-gray-300">
          Import Document
        </h3>
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="file"
            ref={fileRef}
            onChange={handleUpload}
            accept=".pdf,.docx,.txt,.md"
            className="block w-full max-w-xs text-sm text-gray-400 file:mr-3 file:cursor-pointer file:rounded-lg file:border-0 file:bg-indigo-600 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-white hover:file:bg-indigo-500"
          />
          <select
            value={collectionFilter}
            onChange={(e) => setCollectionFilter(e.target.value)}
            className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-indigo-500"
          >
            <option value="">Default collection</option>
            {collections.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          {uploadBusy && (
            <span className="text-sm text-amber-400">Uploading…</span>
          )}
        </div>
        {uploadError && (
          <p className="mt-2 text-sm text-red-400">{uploadError}</p>
        )}
      </div>

      {/* Documents table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-xs uppercase tracking-wider text-gray-500">
              <th className="pb-3 pr-4">Filename</th>
              <th className="pb-3 pr-4">Collection</th>
              <th className="pb-3 pr-4">Size</th>
              <th className="pb-3 pr-4">Status</th>
              <th className="pb-3 pr-4">Chunks</th>
              <th className="pb-3 pr-4">Created</th>
              <th className="pb-3" />
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-gray-500">
                  No documents yet. Upload a PDF, DOCX, TXT, or MD file above.
                </td>
              </tr>
            ) : (
              filtered.map((doc) => (
                <tr
                  key={doc.id}
                  className="border-b border-gray-800/50 transition hover:bg-gray-800/30"
                >
                  <td className="max-w-48 py-3 pr-4">
                    <p className="truncate text-sm text-gray-200">
                      {doc.filename}
                    </p>
                  </td>
                  <td className="py-3 pr-4">
                    <span className="text-xs text-gray-400">
                      {doc.collection_name}
                    </span>
                  </td>
                  <td className="py-3 pr-4 text-gray-400">
                    {formatSize(doc.filesize)}
                  </td>
                  <td className="py-3 pr-4">
                    <span className={statusBadge(doc.status)}>
                      {doc.status}
                    </span>
                  </td>
                  <td className="py-3 pr-4 text-gray-400">
                    {doc.chunk_count}
                  </td>
                  <td className="py-3 pr-4 text-xs text-gray-500">
                    {doc.created_at
                      ? new Date(doc.created_at).toLocaleDateString()
                      : "—"}
                  </td>
                  <td className="py-3">
                    <div className="flex gap-1">
                      {doc.status === "error" && (
                        <button
                          onClick={() => onRetry(doc.id)}
                          className="rounded-lg px-2 py-1 text-xs text-amber-400 transition hover:bg-amber-900/30"
                          title="Retry ingestion"
                        >
                          Retry
                        </button>
                      )}
                      <button
                        onClick={() => onDelete(doc.id)}
                        className="rounded-lg px-2 py-1 text-xs text-red-400 transition hover:bg-red-900/30"
                        title="Delete document"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────── */
/*  Collections Tab                                                         */
/* ──────────────────────────────────────────────────────────────────────── */

function CollectionsTab({
  collections,
  collectionsInfo,
  onDelete,
}: {
  collections: string[];
  collectionsInfo: Map<string, RAGCollectionInfo>;
  onDelete: (name: string) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-gray-800 text-xs uppercase tracking-wider text-gray-500">
            <th className="pb-3 pr-4">Name</th>
            <th className="pb-3 pr-4">Vectors</th>
            <th className="pb-3 pr-4">Dimensions</th>
            <th className="pb-3 pr-4">Status</th>
            <th className="pb-3" />
          </tr>
        </thead>
        <tbody>
          {collections.length === 0 ? (
            <tr>
              <td colSpan={5} className="py-8 text-center text-gray-500">
                No collections found in Milvus.
              </td>
            </tr>
          ) : (
            collections.map((name) => {
              const info = collectionsInfo.get(name);
              return (
                <tr
                  key={name}
                  className="border-b border-gray-800/50 transition hover:bg-gray-800/30"
                >
                  <td className="py-3 pr-4">
                    <p className="font-medium text-gray-200">{name}</p>
                  </td>
                  <td className="py-3 pr-4 text-gray-400">
                    {info
                      ? info.total_vectors.toLocaleString()
                      : "…"}
                  </td>
                  <td className="py-3 pr-4 text-gray-400">
                    {info ? info.dim : "…"}
                  </td>
                  <td className="py-3 pr-4">
                    {info && (
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                          info.indexing_status === "complete"
                            ? "bg-emerald-900/50 text-emerald-400"
                            : "bg-amber-900/50 text-amber-400"
                        }`}
                      >
                        {info.indexing_status}
                      </span>
                    )}
                  </td>
                  <td className="py-3">
                    <button
                      onClick={() => onDelete(name)}
                      className="rounded-lg px-2 py-1 text-xs text-red-400 transition hover:bg-red-900/30"
                      title="Delete collection"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
