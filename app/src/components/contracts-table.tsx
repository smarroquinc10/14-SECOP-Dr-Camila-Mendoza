"use client";

import * as React from "react";
import {
  type ColumnDef,
  type ColumnFiltersState,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ExternalLink,
  Filter,
  RotateCcw,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { type Contract } from "@/lib/api";
import { cn, fmtDate, moneyCO, truncate } from "@/lib/utils";

interface Props {
  data: Contract[];
  onRowClick: (c: Contract) => void;
  /** Whether any page-level slicer/search is active. */
  pageFiltersActive?: boolean;
  /** Optional reset hook — clears page-level filters + table filters/sort. */
  onResetAll?: () => void;
}

/**
 * Excel-style contracts table.
 *
 * - Sticky header with sort + per-column filter (popover input).
 * - Click on a row → opens the detail dialog (handled by parent).
 * - "SECOP ↗" link per row goes straight to the public portal.
 * - Money / dates / state are formatted in-cell.
 */
export function ContractsTable({
  data,
  onRowClick,
  pageFiltersActive = false,
  onResetAll,
}: Props) {
  const [sorting, setSorting] = React.useState<SortingState>([
    { id: "fecha_de_firma", desc: true },
  ]);
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([]);

  const columns = React.useMemo<ColumnDef<Contract>[]>(
    () => [
      {
        accessorKey: "id_contrato",
        header: "Código",
        cell: (info) => (
          <span className="font-mono text-xs text-ink-soft">
            {info.getValue<string>() ?? "—"}
          </span>
        ),
        size: 140,
      },
      {
        accessorKey: "objeto_del_contrato",
        header: "Objeto",
        cell: (info) => (
          <span className="text-sm text-ink line-clamp-2 max-w-md">
            {truncate(info.getValue<string>(), 120)}
          </span>
        ),
      },
      {
        accessorKey: "proveedor_adjudicado",
        header: "Proveedor",
        cell: (info) => (
          <span className="text-sm text-ink truncate block max-w-[220px]">
            {info.getValue<string>() ?? "—"}
          </span>
        ),
      },
      {
        accessorKey: "valor_del_contrato",
        header: "Valor (COP)",
        cell: (info) => {
          const v = Number(info.getValue<string>() ?? 0);
          if (!v) return <span className="text-ink-soft">—</span>;
          return (
            <span className="text-sm font-mono text-ink tabular-nums">
              {moneyCO.format(v)}
            </span>
          );
        },
        sortingFn: (a, b, id) =>
          Number(a.getValue<string>(id) ?? 0) - Number(b.getValue<string>(id) ?? 0),
        size: 130,
      },
      {
        accessorKey: "fecha_de_firma",
        header: "Firma",
        cell: (info) => (
          <span className="text-sm font-mono text-ink-soft tabular-nums">
            {fmtDate(info.getValue<string>())}
          </span>
        ),
        size: 110,
      },
      {
        accessorKey: "estado_contrato",
        header: "Estado",
        cell: (info) => {
          const v = info.getValue<string>() ?? "";
          if (!v) return null;
          const isMod = v.toLowerCase().includes("modific");
          return (
            <Badge
              className={cn(
                isMod
                  ? "bg-burgundy/10 text-burgundy border-burgundy/20"
                  : "bg-stone-100 text-ink border-stone-200"
              )}
            >
              {v}
            </Badge>
          );
        },
        size: 130,
      },
      {
        accessorKey: "_notas",
        header: "Notas",
        cell: (info) => (
          <span className="text-xs text-ink-soft italic">
            {info.getValue<string>() || ""}
          </span>
        ),
      },
      {
        accessorKey: "urlproceso",
        header: "SECOP",
        cell: (info) => {
          const url = info.getValue<string>();
          if (!url) return <span className="text-ink-soft">—</span>;
          return (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-1 text-xs text-burgundy hover:underline"
            >
              Abrir <ExternalLink className="h-3 w-3" />
            </a>
          );
        },
        size: 90,
      },
    ],
    []
  );

  // Custom filter shape: text-contains OR checkbox-list (Excel-style).
  type FilterVal =
    | { kind: "text"; q: string }
    | { kind: "set"; values: string[] };

  const table = useReactTable({
    data,
    columns,
    state: { sorting, columnFilters },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    enableColumnFilters: true,
    defaultColumn: {
      filterFn: (row, colId, filterValue) => {
        const fv = filterValue as FilterVal | undefined;
        if (!fv) return true;
        if (fv.kind === "set") {
          if (fv.values.length === 0) return true;
          return fv.values.includes(String(row.getValue(colId) ?? ""));
        }
        const q = (fv.q ?? "").toLowerCase();
        if (!q) return true;
        return String(row.getValue(colId) ?? "").toLowerCase().includes(q);
      },
    },
  });

  // Derive unique values per column for the Excel-style checkbox list.
  // Capped at 200 distinct values for performance.
  const uniqueValuesByCol = React.useMemo(() => {
    const m: Record<string, string[]> = {};
    for (const c of columns) {
      const id = (c as { accessorKey?: string }).accessorKey;
      if (!id) continue;
      const set = new Set<string>();
      for (const row of data) {
        const v = (row as Record<string, unknown>)[id];
        if (v == null || v === "") continue;
        set.add(String(v));
        if (set.size > 200) break;
      }
      m[id] = Array.from(set).sort();
    }
    return m;
  }, [data, columns]);

  // Consider "default" = sort by Firma DESC + no column filters.
  // Anything else (custom sort or any filter) is a "personalized" view.
  const isDefaultSort =
    sorting.length === 0 ||
    (sorting.length === 1 &&
      sorting[0].id === "fecha_de_firma" &&
      sorting[0].desc);
  const hasActiveFilters =
    !isDefaultSort || columnFilters.length > 0 || pageFiltersActive;

  function resetFormat() {
    setSorting([{ id: "fecha_de_firma", desc: true }]);
    setColumnFilters([]);
    onResetAll?.();
  }

  return (
    <div className="border border-rule rounded-lg overflow-hidden bg-background">
      {hasActiveFilters && (
        <div className="flex items-center justify-between px-4 py-2 bg-amber-50 border-b border-amber-200 text-xs">
          <span className="text-amber-800">
            <Filter className="h-3 w-3 inline mr-1" />
            Tabla con filtros u ordenamiento personalizado.
          </span>
          <button
            onClick={resetFormat}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-amber-600 text-white hover:bg-amber-700 text-xs font-medium"
          >
            <RotateCcw className="h-3 w-3" />
            Restablecer formato
          </button>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-surface border-b border-rule">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => (
                  <th
                    key={h.id}
                    style={{ width: h.column.columnDef.size }}
                    className="text-left px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-ink-soft"
                  >
                    {h.isPlaceholder ? null : (
                      <ColumnHeader
                        title={String(
                          flexRender(h.column.columnDef.header, h.getContext())
                        )}
                        column={h.column}
                        uniqueValues={
                          uniqueValuesByCol[
                            (h.column.columnDef as { accessorKey?: string })
                              .accessorKey ?? ""
                          ] ?? []
                        }
                      />
                    )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="text-center p-12 text-ink-soft italic"
                >
                  Sin resultados con los filtros actuales.
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  onClick={() => onRowClick(row.original)}
                  className="border-b border-rule/60 hover:bg-surface cursor-pointer transition-colors"
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-3 py-2.5 align-middle">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="px-4 py-2.5 text-xs text-ink-soft border-t border-rule bg-surface">
        {table.getRowModel().rows.length} de {data.length} contratos · click cualquier fila para ver detalle completo
      </div>
    </div>
  );
}

/** Excel-style filter header: sort + popover with search + checkbox list.
 *
 * The popover closes on outside-click thanks to Radix Popover, so the
 * Dra. doesn't have to chase down a stuck dropdown. Multi-select pills
 * (the checkbox list) match Excel's "filter by value" UI exactly.
 */
function ColumnHeader({
  title,
  column,
  uniqueValues,
}: {
  title: string;
  column: ReturnType<ReturnType<typeof useReactTable<Contract>>["getColumn"]>;
  uniqueValues: string[];
}) {
  type FilterVal =
    | { kind: "text"; q: string }
    | { kind: "set"; values: string[] };

  const filterValue = column?.getFilterValue() as FilterVal | undefined;
  const isActive =
    !!filterValue &&
    ((filterValue.kind === "set" && filterValue.values.length > 0) ||
      (filterValue.kind === "text" && filterValue.q.length > 0));
  const sort = column?.getIsSorted();

  const [search, setSearch] = React.useState("");
  const selected = filterValue?.kind === "set" ? filterValue.values : [];

  const filteredValues = uniqueValues.filter((v) =>
    v.toLowerCase().includes(search.toLowerCase())
  );

  function toggleValue(v: string) {
    const cur = filterValue?.kind === "set" ? filterValue.values : [];
    const next = cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v];
    column?.setFilterValue({ kind: "set", values: next });
  }

  function selectAll() {
    column?.setFilterValue({ kind: "set", values: filteredValues });
  }

  function clearAll() {
    column?.setFilterValue(undefined);
    setSearch("");
  }

  return (
    <div className="flex items-center gap-1 group">
      <button
        onClick={() => column?.toggleSorting(sort === "asc")}
        className="inline-flex items-center gap-1 hover:text-ink"
      >
        {title}
        {sort === "asc" ? (
          <ArrowUp className="h-3 w-3 opacity-70" />
        ) : sort === "desc" ? (
          <ArrowDown className="h-3 w-3 opacity-70" />
        ) : (
          <ArrowUpDown className="h-3 w-3 opacity-30 group-hover:opacity-70" />
        )}
      </button>
      <Popover>
        <PopoverTrigger asChild>
          <button
            className={cn(
              "inline-flex items-center justify-center h-5 w-5 rounded transition-opacity",
              isActive
                ? "bg-burgundy/10 text-burgundy opacity-100"
                : "opacity-40 group-hover:opacity-100 hover:bg-stone-200"
            )}
            title="Filtrar columna"
          >
            <Filter className="h-3 w-3" />
          </button>
        </PopoverTrigger>
        <PopoverContent className="w-72 p-3">
          <Input
            placeholder="Buscar valor…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 text-xs"
          />
          <div className="flex items-center justify-between mt-2 mb-1 px-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
              {filteredValues.length} valores
            </span>
            <button
              onClick={selectAll}
              className="text-[11px] uppercase tracking-wider text-burgundy hover:underline"
            >
              Seleccionar todos
            </button>
          </div>
          <div className="max-h-64 overflow-y-auto border border-rule rounded">
            {filteredValues.length === 0 ? (
              <div className="px-3 py-6 text-xs italic text-ink-soft text-center">
                Sin valores
              </div>
            ) : (
              filteredValues.map((v) => (
                <label
                  key={v}
                  className="flex items-center gap-2 px-2 py-1.5 hover:bg-surface cursor-pointer text-xs"
                >
                  <Checkbox
                    checked={selected.includes(v)}
                    onCheckedChange={() => toggleValue(v)}
                  />
                  <span className="truncate text-ink">{v}</span>
                </label>
              ))
            )}
          </div>
          <div className="flex justify-between mt-3 pt-2 border-t border-rule">
            <Button variant="ghost" size="sm" onClick={clearAll}>
              Limpiar
            </Button>
            <span className="text-[10px] text-ink-soft self-center">
              {selected.length} seleccionados
            </span>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}
