# AlphaNest public component style contract

Use the established stock-detail components as the visual baseline. New public
surfaces should reuse these values unless the element is a floating menu,
popover, dialog, or another layer that must visibly sit above the page.

## Core tokens

- Card radius: `16px`
- Card padding: `14px` on narrow layouts, `18px` otherwise
- Component gutter: `12px` on narrow layouts, `18px` otherwise
- Card shadow: `0 1px 3px rgba(0,0,0,0.04)`
- Text weights: `600` for supporting copy, `700` for labels, `800` for titles
- Page title: `20px` to `23px`, weight `800`
- Section title: `14px` to `17px`, weight `800`
- Metric label/value: `10.5px / 14px`, weights `700 / 800`

## Reference components

- `PublicStockDetailKR.tsx`
- `PublicCompanyReports.tsx`
- `PublicLiveChart.tsx`

Deep shadows are reserved for floating search results, menus, popovers, and
dialogs. They must not be reused as the default elevation for page cards.
