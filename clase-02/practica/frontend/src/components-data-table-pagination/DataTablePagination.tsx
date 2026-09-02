import {
        ChevronLeft,
        ChevronRight,
        ChevronsLeft,
        ChevronsRight,
} from "lucide-react";
import type { Table } from "@tanstack/react-table";

import { Button } from "./ui/button";
import {
        Select,
        SelectContent,
        SelectGroup,
        SelectItem,
        SelectTrigger,
        SelectValue,
} from "./ui/select";

interface DataTablePaginationProps<TData> {
        table: Table<TData>;
        totalItems?: number;
        entityName?: string;
}

export function DataTablePagination<TData>({
        table,
        totalItems,
        entityName = "registros",
}: DataTablePaginationProps<TData>) {
        return (
                <div className="flex flex-col gap-3 px-2 md:flex-row md:items-center md:justify-between">
                        <div className="text-sm text-muted-foreground md:flex-1">
                                {totalItems === undefined
                                        ? `${table.getFilteredRowModel().rows.length} ${entityName}`
                                        : `${totalItems} ${entityName} en total`}
                        </div>
                        <div className="flex flex-wrap items-center justify-between gap-3 md:flex-nowrap md:justify-end md:gap-6 lg:gap-8">
                                <div className="flex items-center gap-2">
                                        <p className="text-sm font-medium">
                                                Mostrar
                                        </p>
                                        <Select
                                                value={`${table.getState().pagination.pageSize}`}
                                                onValueChange={(value) =>
                                                        table.setPageSize(
                                                                Number(value),
                                                        )
                                                }
                                        >
                                                <SelectTrigger className="min-h-11 w-auto min-w-16 md:h-8 md:min-h-0">
                                                        <SelectValue
                                                                placeholder={
                                                                        table.getState()
                                                                                .pagination
                                                                                .pageSize
                                                                }
                                                        />
                                                </SelectTrigger>
                                                <SelectContent side="top">
                                                        <SelectGroup>
                                                                {[
                                                                        10, 20,
                                                                        30, 40,
                                                                        50,
                                                                ].map(
                                                                        (
                                                                                pageSize,
                                                                        ) => (
                                                                                <SelectItem
                                                                                        key={
                                                                                                pageSize
                                                                                        }
                                                                                        value={`${pageSize}`}
                                                                                >
                                                                                        {
                                                                                                pageSize
                                                                                        }
                                                                                </SelectItem>
                                                                        ),
                                                                )}
                                                        </SelectGroup>
                                                </SelectContent>
                                        </Select>
                                        <p className="text-sm font-medium">
                                                por página
                                        </p>
                                </div>
                                <div className="flex items-center justify-center text-sm font-medium">
                                        Página{" "}
                                        {table.getState().pagination.pageIndex +
                                                1}{" "}
                                        de {table.getPageCount()}
                                </div>
                                <div className="flex items-center gap-2">
                                        <Button
                                                variant="outline"
                                                className="hidden size-8 p-0 lg:flex"
                                                onClick={() =>
                                                        table.setPageIndex(0)
                                                }
                                                disabled={
                                                        !table.getCanPreviousPage()
                                                }
                                        >
                                                <span className="sr-only">
                                                        Ir a la primera página
                                                </span>
                                                <ChevronsLeft
                                                        data-icon="inline-start"
                                                        aria-hidden="true"
                                                />
                                        </Button>
                                        <Button
                                                variant="outline"
                                                className="size-11 p-0 md:size-8"
                                                onClick={() =>
                                                        table.previousPage()
                                                }
                                                disabled={
                                                        !table.getCanPreviousPage()
                                                }
                                        >
                                                <span className="sr-only">
                                                        Ir a la página anterior
                                                </span>
                                                <ChevronLeft
                                                        data-icon="inline-start"
                                                        aria-hidden="true"
                                                />
                                        </Button>
                                        <Button
                                                variant="outline"
                                                className="size-11 p-0 md:size-8"
                                                onClick={() => table.nextPage()}
                                                disabled={
                                                        !table.getCanNextPage()
                                                }
                                        >
                                                <span className="sr-only">
                                                        Ir a la página siguiente
                                                </span>
                                                <ChevronRight
                                                        data-icon="inline-start"
                                                        aria-hidden="true"
                                                />
                                        </Button>
                                        <Button
                                                variant="outline"
                                                className="hidden size-8 p-0 lg:flex"
                                                onClick={() =>
                                                        table.setPageIndex(
                                                                table.getPageCount() -
                                                                        1,
                                                        )
                                                }
                                                disabled={
                                                        !table.getCanNextPage()
                                                }
                                        >
                                                <span className="sr-only">
                                                        Ir a la última página
                                                </span>
                                                <ChevronsRight
                                                        data-icon="inline-start"
                                                        aria-hidden="true"
                                                />
                                        </Button>
                                </div>
                        </div>
                </div>
        );
}
