WITH tamanhos AS (
    SELECT 'P' AS tam UNION ALL
    SELECT 'M' UNION ALL
    SELECT 'G' UNION ALL
    SELECT 'GG' union all
    select 'U'
)
SELECT
    c.material,
    c.cor_insumo,
    cc.codigo2,
    cc.descricao AS descricao_cor,
    mat.descricao AS descricao_mat,
    c.produto,
    c.cor_prod,
    CASE WHEN c.tam = 'U' THEN t.tam ELSE c.tam END AS tam,
    c.consumo
FROM consumoprod c
INNER JOIN material_001 mat ON c.material = mat.codigo
INNER JOIN cadcor_001 cc ON c.cor_insumo = cc.cor
LEFT JOIN tamanhos t
    ON c.tam = 'U'  -- só cruza tamanhos quando é U
WHERE mat.grupo = '02'
  AND mat.sub_grupo IN ('08','019','021','023')
  AND (c.tam <> 'U' OR t.tam IS NOT NULL)  -- garante que U gere linhas via tamanhos
  
ORDER BY c.material, c.cor_insumo, tam;