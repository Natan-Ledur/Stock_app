import pandas as pd
# Reload trigger
import numpy as np
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

def format_number_br(val, decimals=None):
    """Formata um número no padrão brasileiro (milhares com ponto, decimais com vírgula).

    Parâmetros:
    - val: valor numérico ou string representando número.
    - decimals: número de casas decimais desejadas. Se None, preserva a
      quantidade de casas decimais fornecida na entrada (até 8).

    Regras:
    - None / NaN -> string vazia.
    - Preserva sinal negativo.
    - Usa arredondamento HALF_UP.
    """
    if val is None:
        return ""
    if isinstance(val, float) and np.isnan(val):
        return ""

    original_str = str(val).strip()
    # Normaliza separador decimal para ponto para parsing (aceita vírgula vinda já em formato BR)
    if original_str.count(',') == 1 and original_str.count('.') == 0:
        parse_str = original_str.replace(',', '.')
    else:
        # Remove pontos de milhares se vier em formato BR (ex: 1.234,56)
        if original_str.count(',') == 1 and original_str.count('.') >= 1:
            # Assume pontos como milhares e vírgula como decimal
            sem_milhar = original_str.replace('.', '')
            parse_str = sem_milhar.replace(',', '.')
        else:
            parse_str = original_str

    try:
        d = Decimal(parse_str)
    except (InvalidOperation, ValueError):
        # Retorna original se não for número
        return original_str

    # Detecta casas decimais originais se decimals=None
    if decimals is None:
        if '.' in parse_str:
            dec_count = len(parse_str.split('.')[-1])
        else:
            dec_count = 0
        # Limita para evitar exageros (ex: floats binários longos)
        decimals = min(dec_count, 8)

    # Aplica arredondamento se necessário
    if decimals >= 0:
        quant = Decimal('1') if decimals == 0 else Decimal('1.' + ('0' * decimals))
        try:
            d = d.quantize(quant, rounding=ROUND_HALF_UP)
        except InvalidOperation:
            pass

    # Constrói string com milhar usando formatação padrão en_US
    # Usamos float apenas para formatar milhares; para números muito grandes/precisos
    # isso pode perder precisão após arredondamento, mas já quantizamos antes.
    try:
        en_fmt = f"{float(d):,.{decimals}f}" if decimals >= 0 else f"{float(d):,f}"
    except Exception:
        # Fallback sem milhares
        en_fmt = format(d)

    en_fmt = en_fmt.replace('\xa0', '')
    # Troca separadores: vírgula (,) -> marcador temporário '#'; ponto (.) -> vírgula; '#' -> ponto.
    br_fmt = en_fmt.replace(',', '#').replace('.', ',').replace('#', '.')
    return br_fmt

def format_dataframe_brazilian(df: pd.DataFrame, decimals=None, inplace=False, coerce_object_numeric=True):
    """Formata colunas numéricas de um DataFrame para padrão brasileiro.

    Parâmetros:
    - decimals: None preserva casas originais (até 8) por célula; int força casas fixas.
    - inplace: altera DataFrame original se True.
    - coerce_object_numeric: tenta converter colunas 'object' que sejam majoritariamente numéricas.
    """
    if not inplace:
        df = df.copy()

    # Opcional: detectar colunas object potencialmente numéricas (mais de 70% dos valores parseáveis)
    if coerce_object_numeric:
        obj_cols = [c for c in df.columns if df[c].dtype == 'object']
        for col in obj_cols:
            serie = df[col]
            # Ignorar se já contém strings formatadas (vírgula e ponto invertidos) de forma predominante
            sample_non_null = serie.dropna().astype(str).head(50)
            if sample_non_null.empty:
                continue
            parseable = 0
            total = len(sample_non_null)
            for v in sample_non_null:
                v_strip = v.strip()
                if v_strip == '':
                    continue
                # Normaliza possíveis formatos BR para teste
                if v_strip.count(',') == 1 and v_strip.count('.') >= 1:
                    v_test = v_strip.replace('.', '').replace(',', '.')
                elif v_strip.count(',') == 1 and v_strip.count('.') == 0:
                    v_test = v_strip.replace(',', '.')
                else:
                    v_test = v_strip
                try:
                    float(v_test)
                    parseable += 1
                except Exception:
                    pass
            if total > 0 and parseable / total >= 0.7:
                try:
                    df[col] = pd.to_numeric(serie.str.replace('.', '', regex=False).str.replace(',', '.', regex=False), errors='coerce')
                except Exception:
                    try:
                        df[col] = pd.to_numeric(serie, errors='coerce')
                    except Exception:
                        pass

    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    for col in num_cols:
        # Regra especial: 'codigo_tabela_cor' sempre exibido como inteiro (sem casas decimais)
        col_decimals = 0 if col == 'codigo_tabela_cor' else decimals
        try:
            df[col] = df[col].apply(lambda x: format_number_br(x, decimals=col_decimals))
        except Exception:
            df[col] = [format_number_br(x, decimals=col_decimals) for x in df[col].values]
    # Formatar níveis de índice numéricos (caso tenham sido definidos antes da chamada)
    try:
        if isinstance(df.index, pd.MultiIndex):
            new_levels = []
            for lvl in df.index.levels:
                if lvl.dtype.kind in 'if':
                    new_levels.append([format_number_br(v, decimals=decimals) for v in lvl])
                else:
                    new_levels.append(list(lvl))
            # Reconstroi MultiIndex
            df.index = pd.MultiIndex.from_tuples(
                [tuple(new_levels[i][list(df.index.levels[i]).index(val)] for i, val in enumerate(tpl)) for tpl in df.index],
                names=df.index.names
            )
        else:
            if df.index.dtype.kind in 'if':
                df.index = pd.Index([format_number_br(v, decimals=decimals) for v in df.index], name=df.index.name)
    except Exception:
        pass
    return df

def get_color_hex(name):
    """Retorna cor hexadecimal baseada no nome da cor (PT-BR/ES/EN)."""
    name_u = str(name).upper().strip()
    
    # 1. Tentativa de Match Exato (Prioridade)
    exact_map = {
        'BLANCO': '#FFFFFF',
        'NEGRO': '#000000',
        'ROJO': '#FF0000',
        'BORDO': '#800000',
        'MARINO': '#000080',
        'ROSA': '#FFC0CB',
        'SALMON': '#FA8072',
        'CELESTE': '#87CEEB',
        'AZUL 120': '#0047AB',     # Azul Cobalto/Forte
        'AZUL FRANCIA': '#318CE7', # Azul Royal Brilhante
        'GRIS 1': "#D3D3D3",       # Cinza Claro
        'GRIS 2': '#A9A9A9',       # Cinza Médio
        'GRIS 3': "#696969",       # Cinza Escuro
    }
    if name_u in exact_map:
        return exact_map[name_u]

    # 2. Match Parcial (Termos genéricos)
    map_idx = {
        'OFF': '#F8F8FF', 'CRU': '#EEE8AA', 'NATURAL': '#FAF0E6',
        'BRANCO': '#F5F5F5', 'WHITE': '#FFFFFF', 
        'PRETO': '#000000', 'BLACK': '#111111', 'NEGRO': '#000000',
        'MARINHO': '#000080', 'ROYAL': '#4169E1', 'TURQUESA': '#40E0D0', 
        'AZUL': '#0000FF', 'BLUE': '#0000FF', 
        'VERMELHO': '#FF0000', 'RED': '#FF0000', 'VINHO': '#800000', 'CEREJA': '#DE3163', 'ROJO': '#FF0000', 'BORDO': '#800000',
        'VERDE': '#008000', 'GREEN': '#008000', 'MUSGO': '#556B2F', 'OLIVA': '#808000', 'LIMA': '#32CD32',
        'AMARELO': '#FFD700', 'YELLOW': '#FFD700', 'OURO': '#FFD700',
        'ROSA': '#FFC0CB', 'PINK': '#FFC0CB', 'CHOQUE': '#FF69B4', 'MAGENTA': '#FF00FF', 'SALMON': '#FA8072',
        'CHUMBO': '#696969', 'GRAFITE': '#4F4F4F', 'PRATA': '#C0C0C0', 'MESCLA': '#A9A9A9',
        'CINZA': '#808080', 'GREY': '#808080', 'GRIS': '#808080',
        'MARROM': '#8B4513', 'BROWN': '#8B4513', 'TERRA': '#A0522D', 'CAFE': '#4B3621',
        'BEGE': '#F5F5DC', 'NUDE': '#FFE4C4', 'CAQUI': '#F0E68C', 'AREIA': '#F4A460',
        'LARANJA': '#FFA500', 'ORANGE': '#FFA500', 'CORAL': '#FF7F50',
        'ROXO': '#800080', 'PURPLE': '#800080', 'LILAS': '#D8BFD8', 'VIOLETA': '#EE82EE'
    }
    
    for key, hex_val in map_idx.items():
        if key in name_u:
            return hex_val
    return None
