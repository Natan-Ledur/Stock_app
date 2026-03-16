select pi.numero as numero, 
       p.codigo, 
       p.cor, 
       p.cor_i,
       cr.descricao as desc_cor,
       p.faixa, 
       P2.consumo as PROPORCAO,
       p2.QTDE as GRADE, 
       PI.QTDE as QTDE_TOTAL_PED,
       ((p2.consumo /p2.qtde)* pi.qtde) as QTDE_POR_COR, 
       cast((((p2.consumo /p2.qtde)* pi.qtde)/12) as int) as DUZIAS,
       (((p2.consumo /p2.qtde)* pi.qtde) / prod.quant) as canastas,
       fi.posicao 
--p., p2.
from pcpft3_001 p 
inner join produto_001 PROD on (PROD.CODIGO = p.INSUMO)
left join pcpft2_001 p2 on(p2.codigo = p.codigo and p2.insumo = p.insumo and p.id = p2.id)
left join faixa_iten_001 fi on(fi.tamanho = p.faixa and fi.faixa = prod.faixa)
left join cadcor_001 cr on(cr.cor = p.cor_i)
left join ped_iten_001 pi on(pi.codigo = p.codigo and pi.cor = p.cor and pi.tam = p.faixa)
where 
p.cor_i not like '%***%'
and PROD.ETIQUETA = '02'
and pi.numero in  (:sel)
 
order by p.codigo,  fi.posicao