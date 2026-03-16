select
pc3.cor,
pc3.cor_i,	
PCPFT2.codigo,
pcpft2.insumo,
pcpft2.faixa,
	case
		when PCPFT2.TIPO = 'P' then case
			when ((PRODUTO.DESCRICAO is not null )
			and (PRODUTO.DESCRICAO <> '')) then PRODUTO.DESCRICAO
			else PROTOTIPO.DESCRICAO
		end
		else MATERIAL.DESCRICAO
	end DESCRICAO,
	case
		when PCPFT2.TIPO = 'P' then PRODUTO.UNIDADE
		else MATERIAL.UNIDADE
	end UNIDADE,
	PCPAPL.DESCRICAO DESC_APL,
	TIPO_APL.DESCRICAO DESC_PARTE
from
	PCPFT2_001 PCPFT2
left join MATERIAL_001 MATERIAL on
	(PCPFT2.INSUMO = MATERIAL.CODIGO)
left join PRODUTO_001 PRODUTO on
	(PCPFT2.INSUMO = PRODUTO.CODIGO)
left join PRODUTO_001 PROTOTIPO on
	((coalesce(PRODUTO.CODIGO, '') = '')
		and PCPFT2.INSUMO = PROTOTIPO.PROTOTIPO
		and ((PROTOTIPO.PROTOTIPO is not null )
			and (PROTOTIPO.PROTOTIPO <> '')) )
left join PCPAPL_001 PCPAPL on
	(PCPAPL.CODIGO = PCPFT2.APLICACAO)
left join TIPO_APL_001 TIPO_APL on
	(PCPFT2.PARTE = TIPO_APL.CODIGO)
left join MAQUINA_001 MAQ on
	(MAQ.MAQUINA = PCPFT2.MAQUINA)
	inner join pcpft3_001 pc3 on PCPFT2.insumo = pc3.insumo	
	inner join produto_001 pr on PCPFT2.codigo = pr.codigo
where
	pcpft2.tipo='P'  and not pc3.cor_i='*****'
	and pcpft2.faixa in ('U', 'P', 'M', 'G', 'GG')
order by
	PCPFT2.ID