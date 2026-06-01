# TODO

- Refactor query-param synchronization so `RouteContext` stays a route read model. Move `QueryParamSync` ownership to the mounted route/render layer, with live route data used for reads and immutable route origin used for guarded URL writes.
