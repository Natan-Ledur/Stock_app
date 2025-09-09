SELECT
		c.material,
		c.cor_insumo,
		cc.codigo2,
		cc.descricao as descricao_cor,
		mat.descricao as descricao_mat,
		c.produto,
		c.cor_prod,
		c.tam,
		c.consumo		
FROM consumoprod c
INNER JOIN material_001 mat ON c.material = mat.codigo
inner join cadcor_001 cc on c.cor_insumo = cc.cor 
where mat.grupo =  '02' and mat.sub_grupo in ('08','019','021','023')
order by c.material,
		 c.cor_insumo, c.tam 

