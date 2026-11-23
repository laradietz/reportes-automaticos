-- Ventas por categoría de producto.
SELECT pr.categoria,
       SUM(v.cantidad)                                           AS unidades,
       ROUND(SUM(v.importe_neto), 2)                             AS ventas_netas,
       ROUND(100.0 * SUM(v.importe_neto) / SUM(SUM(v.importe_neto)) OVER (), 1) AS participacion_pct
FROM fact_ventas v JOIN dim_producto pr ON pr.id_producto = v.id_producto
GROUP BY pr.categoria
ORDER BY ventas_netas DESC;
