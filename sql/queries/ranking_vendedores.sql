-- Ranking de vendedores.
SELECT RANK() OVER (ORDER BY SUM(importe_neto) DESC) AS ranking,
       vendedor,
       COUNT(*)                                       AS ordenes,
       ROUND(SUM(importe_neto), 2)                    AS ventas_netas,
       ROUND(SUM(importe_neto) * 1.0 / COUNT(*), 2)   AS ticket_promedio,
       ROUND(100.0 * AVG(descuento), 1)               AS descuento_promedio_pct
FROM fact_ventas
GROUP BY vendedor
ORDER BY ranking;
