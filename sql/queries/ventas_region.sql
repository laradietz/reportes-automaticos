-- Ventas por región y participación sobre el total.
SELECT c.region,
       COUNT(DISTINCT v.id_cliente)                              AS clientes_activos,
       COUNT(*)                                                  AS ordenes,
       ROUND(SUM(v.importe_neto), 2)                             AS ventas_netas,
       ROUND(100.0 * SUM(v.importe_neto) / SUM(SUM(v.importe_neto)) OVER (), 1) AS participacion_pct,
       ROUND(SUM(v.importe_neto) * 1.0 / COUNT(*), 2)            AS ticket_promedio
FROM fact_ventas v JOIN dim_cliente c ON c.id_cliente = v.id_cliente
GROUP BY c.region
ORDER BY ventas_netas DESC;
