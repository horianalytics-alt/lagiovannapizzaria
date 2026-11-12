"""Regras de negócio: montagem de pedidos, comandas, fechamento de conta e indicadores."""
from collections import defaultdict
from datetime import date, datetime, timedelta

from .db import agora

FORMAS_PAGAMENTO = ("dinheiro", "pix", "credito", "debito")
STATUS_PEDIDO = ("pendente", "preparo", "pronto", "entregue", "cancelado")
MAX_ITENS = 40
MAX_QUANTIDADE = 20


class Erro(Exception):
    def __init__(self, mensagem, codigo=400):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.codigo = codigo


def reais(centavos):
    return f"R$ {centavos / 100:.2f}".replace(".", ",")


def _inteiro(valor, campo, minimo=None, maximo=None):
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise Erro(f"{campo} inválido.")
    if minimo is not None and valor < minimo or maximo is not None and valor > maximo:
        raise Erro(f"{campo} inválido.")
    return valor


def _texto(valor, limite):
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise Erro("Texto inválido.")
    valor = " ".join(valor.split())
    return valor[:limite] or None


def _produto_disponivel(db, produto_id):
    linha = db.execute(
        """SELECT p.id, p.nome, p.preco, c.tipo
           FROM produtos p JOIN categorias c ON c.id = p.categoria_id
           WHERE p.id = ? AND p.ativo = 1 AND p.excluido = 0 AND c.ativo = 1 AND c.excluido = 0""",
        (produto_id,),
    ).fetchone()
    if not linha:
        raise Erro("Um dos itens não está mais disponível no cardápio. Atualize e tente de novo.", 409)
    return linha


def montar_itens(db, itens_req):
    """Valida os itens recebidos e calcula descrição e preço no servidor."""
    if not isinstance(itens_req, list) or not itens_req:
        raise Erro("O pedido está vazio.")
    if len(itens_req) > MAX_ITENS:
        raise Erro("Pedido com itens demais. Divida em pedidos menores.")
    itens = []
    for bruto in itens_req:
        if not isinstance(bruto, dict):
            raise Erro("Item inválido.")
        produto = _produto_disponivel(db, _inteiro(bruto.get("produto_id"), "Produto"))
        quantidade = _inteiro(bruto.get("quantidade", 1), "Quantidade", 1, MAX_QUANTIDADE)
        descricao, preco, detalhe = produto["nome"], produto["preco"], None
        produto2_id = borda_id = None

        if bruto.get("produto2_id") is not None:
            if produto["tipo"] != "pizza":
                raise Erro("Só pizzas podem ser meio a meio.")
            produto2 = _produto_disponivel(db, _inteiro(bruto["produto2_id"], "Segundo sabor"))
            if produto2["tipo"] != "pizza":
                raise Erro("Só pizzas podem ser meio a meio.")
            if produto2["id"] != produto["id"]:
                produto2_id = produto2["id"]
                descricao = f"½ {produto['nome']} + ½ {produto2['nome']}"
                preco = max(produto["preco"], produto2["preco"])

        if bruto.get("borda_id") is not None:
            if produto["tipo"] != "pizza":
                raise Erro("Só pizzas podem ter borda recheada.")
            borda = db.execute(
                "SELECT id, nome, preco FROM bordas WHERE id = ? AND ativo = 1 AND excluido = 0",
                (_inteiro(bruto["borda_id"], "Borda"),),
            ).fetchone()
            if not borda:
                raise Erro("A borda escolhida não está mais disponível.", 409)
            borda_id = borda["id"]
            detalhe = f"Borda {borda['nome']}"
            preco += borda["preco"]

        itens.append(
            dict(
                produto_id=produto["id"],
                produto2_id=produto2_id,
                borda_id=borda_id,
                descricao=descricao,
                detalhe=detalhe,
                observacao=_texto(bruto.get("observacao"), 200),
                quantidade=quantidade,
                preco_unit=preco,
            )
        )
    return itens


def mesa_por_numero(db, numero):
    mesa = db.execute("SELECT * FROM mesas WHERE numero = ? AND ativo = 1", (numero,)).fetchone()
    if not mesa:
        raise Erro("Mesa não encontrada. Peça ajuda a um garçom.", 404)
    return mesa


def mesa_por_id(db, mesa_id):
    mesa = db.execute("SELECT * FROM mesas WHERE id = ? AND ativo = 1", (mesa_id,)).fetchone()
    if not mesa:
        raise Erro("Mesa não encontrada.", 404)
    return mesa


def comanda_aberta(db, mesa_id):
    return db.execute(
        "SELECT * FROM comandas WHERE mesa_id = ? AND status = 'aberta'", (mesa_id,)
    ).fetchone()


def criar_pedido(db, mesa, itens_req, origem, usuario_id=None):
    itens = montar_itens(db, itens_req)
    momento = agora()
    with db:
        comanda = comanda_aberta(db, mesa["id"])
        if comanda:
            comanda_id = comanda["id"]
        else:
            comanda_id = db.execute(
                "INSERT INTO comandas (mesa_id, aberta_em) VALUES (?, ?)", (mesa["id"], momento)
            ).lastrowid
        pedido_id = db.execute(
            """INSERT INTO pedidos (comanda_id, mesa_id, origem, usuario_id, criado_em, atualizado_em)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (comanda_id, mesa["id"], origem, usuario_id, momento, momento),
        ).lastrowid
        db.executemany(
            """INSERT INTO pedido_itens
               (pedido_id, produto_id, produto2_id, borda_id, descricao, detalhe, observacao, quantidade, preco_unit)
               VALUES (:pedido_id, :produto_id, :produto2_id, :borda_id, :descricao, :detalhe, :observacao,
                       :quantidade, :preco_unit)""",
            [dict(item, pedido_id=pedido_id) for item in itens],
        )
    return pedido_id


def _pedidos_com_itens(db, onde, parametros):
    pedidos = [
        dict(linha)
        for linha in db.execute(
            f"""SELECT p.id, p.comanda_id, p.mesa_id, m.numero AS mesa, p.origem, p.status,
                       p.criado_em, p.atualizado_em, u.nome AS atendente
                FROM pedidos p JOIN mesas m ON m.id = p.mesa_id
                LEFT JOIN usuarios u ON u.id = p.usuario_id
                WHERE {onde} ORDER BY p.criado_em, p.id""",
            parametros,
        )
    ]
    if not pedidos:
        return []
    por_id = {p["id"]: p for p in pedidos}
    for p in pedidos:
        p["itens"] = []
        p["total"] = 0
    marcas = ",".join("?" * len(pedidos))
    for item in db.execute(
        f"""SELECT id, pedido_id, descricao, detalhe, observacao, quantidade, preco_unit, cancelado
            FROM pedido_itens WHERE pedido_id IN ({marcas}) ORDER BY id""",
        list(por_id),
    ):
        pedido = por_id[item["pedido_id"]]
        pedido["itens"].append(dict(item))
        if not item["cancelado"] and pedido["status"] != "cancelado":
            pedido["total"] += item["quantidade"] * item["preco_unit"]
    return pedidos


def pedidos_da_comanda(db, comanda_id):
    return _pedidos_com_itens(db, "p.comanda_id = ?", (comanda_id,))


def pedidos_da_cozinha(db):
    """Fila da cozinha: tudo que está pendente ou em preparo, e os prontos da última meia hora."""
    limite = (datetime.now() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    return _pedidos_com_itens(
        db,
        """p.status IN ('pendente', 'preparo') OR (p.status = 'pronto' AND p.atualizado_em >= ?)""",
        (limite,),
    )


def subtotal_comanda(db, comanda_id):
    return db.execute(
        """SELECT COALESCE(SUM(i.quantidade * i.preco_unit), 0)
           FROM pedido_itens i JOIN pedidos p ON p.id = i.pedido_id
           WHERE p.comanda_id = ? AND p.status != 'cancelado' AND i.cancelado = 0""",
        (comanda_id,),
    ).fetchone()[0]


def situacao_mesa(db, mesa):
    """Resumo de uma mesa para o cliente, o garçom e o caixa."""
    comanda = comanda_aberta(db, mesa["id"])
    dados = dict(
        id=mesa["id"],
        numero=mesa["numero"],
        chamado=mesa["chamado"],
        chamado_em=mesa["chamado_em"],
        status="aguardando" if mesa["chamado"] else ("ocupada" if comanda else "livre"),
        comanda_id=None,
        aberta_em=None,
        subtotal=0,
        pedidos=[],
    )
    if comanda:
        dados.update(
            comanda_id=comanda["id"],
            aberta_em=comanda["aberta_em"],
            subtotal=subtotal_comanda(db, comanda["id"]),
            pedidos=pedidos_da_comanda(db, comanda["id"]),
        )
    return dados


def listar_mesas(db):
    mesas = []
    for mesa in db.execute("SELECT * FROM mesas WHERE ativo = 1 ORDER BY numero"):
        dados = situacao_mesa(db, mesa)
        pedidos = dados.pop("pedidos")
        dados["pedidos_prontos"] = sum(1 for p in pedidos if p["status"] == "pronto")
        dados["pedidos_em_andamento"] = sum(1 for p in pedidos if p["status"] in ("pendente", "preparo"))
        mesas.append(dados)
    return mesas


def mudar_status_pedido(db, pedido_id, novo_status, perfil):
    if novo_status not in STATUS_PEDIDO:
        raise Erro("Status inválido.")
    permitidos = {
        "cozinha": {"pendente", "preparo", "pronto"},
        "garcom": {"entregue", "cancelado"},
        "admin": set(STATUS_PEDIDO),
    }[perfil]
    if novo_status not in permitidos:
        raise Erro("Seu perfil não pode fazer essa mudança.", 403)
    pedido = db.execute(
        """SELECT p.id, p.status, c.status AS comanda_status
           FROM pedidos p JOIN comandas c ON c.id = p.comanda_id WHERE p.id = ?""",
        (pedido_id,),
    ).fetchone()
    if not pedido:
        raise Erro("Pedido não encontrado.", 404)
    if pedido["comanda_status"] != "aberta":
        raise Erro("A conta desta mesa já foi fechada.", 409)
    if pedido["status"] == "cancelado":
        raise Erro("Este pedido foi cancelado.", 409)
    if perfil == "garcom" and novo_status == "cancelado" and pedido["status"] != "pendente":
        raise Erro("A cozinha já começou este pedido. Peça o cancelamento ao gerente.", 409)
    with db:
        db.execute(
            "UPDATE pedidos SET status = ?, atualizado_em = ? WHERE id = ?",
            (novo_status, agora(), pedido_id),
        )


def estornar_item(db, item_id):
    item = db.execute(
        """SELECT i.id, c.status AS comanda_status
           FROM pedido_itens i JOIN pedidos p ON p.id = i.pedido_id
           JOIN comandas c ON c.id = p.comanda_id WHERE i.id = ?""",
        (item_id,),
    ).fetchone()
    if not item:
        raise Erro("Item não encontrado.", 404)
    if item["comanda_status"] != "aberta":
        raise Erro("A conta desta mesa já foi fechada.", 409)
    with db:
        db.execute("UPDATE pedido_itens SET cancelado = 1 WHERE id = ?", (item_id,))


def calcular_conta(subtotal, desconto, taxa_pct):
    taxa = round(subtotal * taxa_pct / 100)
    return taxa, subtotal - desconto + taxa


def fechar_conta(db, mesa, desconto, taxa_pct, pagamentos, usuario_id):
    comanda = comanda_aberta(db, mesa["id"])
    if not comanda:
        raise Erro("Esta mesa não tem conta aberta.", 409)
    subtotal = subtotal_comanda(db, comanda["id"])
    desconto = _inteiro(desconto, "Desconto", 0)
    if desconto > subtotal:
        raise Erro("O desconto não pode ser maior que o consumo.")
    if isinstance(taxa_pct, bool) or not isinstance(taxa_pct, (int, float)) or not 0 <= taxa_pct <= 30:
        raise Erro("Taxa de serviço inválida (use de 0 a 30%).")
    taxa, total = calcular_conta(subtotal, desconto, taxa_pct)

    if not isinstance(pagamentos, list):
        raise Erro("Pagamentos inválidos.")
    registros = []
    for pagamento in pagamentos:
        if not isinstance(pagamento, dict) or pagamento.get("forma") not in FORMAS_PAGAMENTO:
            raise Erro("Forma de pagamento inválida.")
        registros.append((comanda["id"], pagamento["forma"], _inteiro(pagamento.get("valor"), "Valor", 1)))
    pago = sum(r[2] for r in registros)
    if pago != total:
        raise Erro(f"Os pagamentos somam {reais(pago)}, mas o total da conta é {reais(total)}.")

    momento = agora()
    with db:
        db.execute(
            """UPDATE pedidos SET status = 'entregue', atualizado_em = ?
               WHERE comanda_id = ? AND status IN ('pendente', 'preparo', 'pronto')""",
            (momento, comanda["id"]),
        )
        db.executemany("INSERT INTO pagamentos (comanda_id, forma, valor) VALUES (?, ?, ?)", registros)
        db.execute(
            """UPDATE comandas SET status = 'fechada', fechada_em = ?, subtotal = ?, desconto = ?,
                      taxa_servico_pct = ?, taxa_servico = ?, total = ?, fechada_por = ?
               WHERE id = ?""",
            (momento, subtotal, desconto, taxa_pct, taxa, total, usuario_id, comanda["id"]),
        )
        db.execute("UPDATE mesas SET chamado = NULL, chamado_em = NULL WHERE id = ?", (mesa["id"],))
    return dict(comanda_id=comanda["id"], subtotal=subtotal, desconto=desconto, taxa_servico=taxa, total=total)


def contas_fechadas(db, dia):
    contas = []
    for linha in db.execute(
        """SELECT c.id, m.numero AS mesa, c.aberta_em, c.fechada_em, c.subtotal, c.desconto,
                  c.taxa_servico, c.total, u.nome AS fechada_por
           FROM comandas c JOIN mesas m ON m.id = c.mesa_id
           LEFT JOIN usuarios u ON u.id = c.fechada_por
           WHERE c.status = 'fechada' AND date(c.fechada_em) = ? ORDER BY c.fechada_em DESC""",
        (dia,),
    ):
        conta = dict(linha)
        conta["pagamentos"] = [
            dict(p)
            for p in db.execute("SELECT forma, valor FROM pagamentos WHERE comanda_id = ?", (conta["id"],))
        ]
        contas.append(conta)
    return contas


def indicadores(db, dia=None):
    dia = dia or date.today().isoformat()
    try:
        referencia = date.fromisoformat(dia)
    except ValueError:
        raise Erro("Data inválida.")

    faturamento, contas = db.execute(
        """SELECT COALESCE(SUM(total), 0), COUNT(*) FROM comandas
           WHERE status = 'fechada' AND date(fechada_em) = ?""",
        (dia,),
    ).fetchone()
    pedidos = db.execute(
        "SELECT COUNT(*) FROM pedidos WHERE date(criado_em) = ? AND status != 'cancelado'", (dia,)
    ).fetchone()[0]

    em_aberto = mesas_abertas = 0
    if referencia == date.today():
        for comanda in db.execute("SELECT id FROM comandas WHERE status = 'aberta'"):
            em_aberto += subtotal_comanda(db, comanda["id"])
            mesas_abertas += 1

    por_hora = defaultdict(int)
    for linha in db.execute(
        """SELECT CAST(strftime('%H', p.criado_em) AS INTEGER) AS hora,
                  SUM(i.quantidade * i.preco_unit) AS valor
           FROM pedido_itens i JOIN pedidos p ON p.id = i.pedido_id
           WHERE date(p.criado_em) = ? AND p.status != 'cancelado' AND i.cancelado = 0
           GROUP BY hora""",
        (dia,),
    ):
        por_hora[linha["hora"]] = linha["valor"]
    if por_hora:
        horas = range(min(por_hora), max(por_hora) + 1)
        vendas_por_hora = [dict(hora=h, valor=por_hora[h]) for h in horas]
    else:
        vendas_por_hora = []

    # Ranking de pizzas: cada metade de uma meio a meio conta como meia pizza do sabor.
    quantidades = defaultdict(float)
    for linha in db.execute(
        """SELECT p1.nome AS sabor1, p2.nome AS sabor2, i.quantidade
           FROM pedido_itens i JOIN pedidos p ON p.id = i.pedido_id
           JOIN produtos p1 ON p1.id = i.produto_id
           JOIN categorias c ON c.id = p1.categoria_id
           LEFT JOIN produtos p2 ON p2.id = i.produto2_id
           WHERE date(p.criado_em) = ? AND p.status != 'cancelado' AND i.cancelado = 0 AND c.tipo = 'pizza'""",
        (dia,),
    ):
        if linha["sabor2"]:
            quantidades[linha["sabor1"]] += linha["quantidade"] / 2
            quantidades[linha["sabor2"]] += linha["quantidade"] / 2
        else:
            quantidades[linha["sabor1"]] += linha["quantidade"]
    ranking = sorted(quantidades.items(), key=lambda par: (-par[1], par[0]))[:8]

    pagamentos = {
        linha["forma"]: linha["valor"]
        for linha in db.execute(
            """SELECT pg.forma, SUM(pg.valor) AS valor FROM pagamentos pg
               JOIN comandas c ON c.id = pg.comanda_id
               WHERE c.status = 'fechada' AND date(c.fechada_em) = ? GROUP BY pg.forma""",
            (dia,),
        )
    }

    inicio = referencia - timedelta(days=6)
    por_dia = {
        linha["dia"]: linha["valor"]
        for linha in db.execute(
            """SELECT date(fechada_em) AS dia, SUM(total) AS valor FROM comandas
               WHERE status = 'fechada' AND date(fechada_em) BETWEEN ? AND ? GROUP BY dia""",
            (inicio.isoformat(), dia),
        )
    }
    ultimos_dias = [
        dict(dia=(inicio + timedelta(days=n)).isoformat(), valor=por_dia.get((inicio + timedelta(days=n)).isoformat(), 0))
        for n in range(7)
    ]

    return dict(
        dia=dia,
        faturamento=faturamento,
        contas_fechadas=contas,
        ticket_medio=round(faturamento / contas) if contas else 0,
        pedidos=pedidos,
        em_aberto=em_aberto,
        mesas_abertas=mesas_abertas,
        vendas_por_hora=vendas_por_hora,
        ranking_pizzas=[dict(nome=nome, quantidade=qtd) for nome, qtd in ranking],
        pagamentos=[dict(forma=f, valor=pagamentos.get(f, 0)) for f in FORMAS_PAGAMENTO],
        ultimos_dias=ultimos_dias,
    )
