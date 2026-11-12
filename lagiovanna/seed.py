"""Dados iniciais: equipe, cardápio, mesas e um movimento fictício para o painel abrir com números."""
import random
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

USUARIOS = [
    ("Giovanna (gerente)", "admin", "giovanna123", "admin"),
    ("Rafael", "garcom", "garcom123", "garcom"),
    ("Cozinha", "cozinha", "cozinha123", "cozinha"),
]

FOTO = "/static/img/cardapio/"

# (categoria, tipo, [(nome, descrição, preço em centavos, foto)])
CARDAPIO = [
    ("Pizzas tradicionais", "pizza", [
        ("Mussarela", "Molho de tomate da casa, mussarela, orégano e azeitonas verdes.", 4990, None),
        ("Calabresa", "Calabresa fatiada, cebola roxa, mussarela e orégano.", 5290, "fatia-calabresa.webp"),
        ("Marguerita", "Mussarela, tomate em rodelas, manjericão fresco e parmesão.", 5490, None),
        ("Portuguesa", "Presunto, ovos, cebola, ervilha, mussarela e azeitonas.", 5890, None),
        ("Frango com catupiry", "Frango desfiado temperado e catupiry original.", 5890, None),
        ("Alho e óleo", "Mussarela coberta com alho dourado no azeite e orégano.", 5190, None),
        ("Napolitana", "Mussarela, tomate, parmesão ralado na hora e manjericão.", 5390, None),
        ("Bacon", "Bacon crocante em cubos sobre mussarela e orégano.", 5990, None),
    ]),
    ("Pizzas especiais", "pizza", [
        ("Pepperoni", "Pepperoni, pimentão verde, mussarela e azeitonas.", 6690, "pepperoni.webp"),
        ("Calabresa com bacon", "Calabresa, bacon dourado, mussarela e um toque de alho.", 6490, "calabresa-alho.webp"),
        ("Quatro queijos", "Mussarela, provolone, gorgonzola e catupiry.", 6690, None),
        ("La Giovanna", "A da casa: lombo canadense, palmito, catupiry, tomate seco e rúcula.", 7290, None),
        ("Carne seca com catupiry", "Carne seca desfiada, catupiry, cebola roxa e cheiro-verde.", 7290, None),
        ("Parma com rúcula", "Presunto parma, rúcula, lascas de parmesão e tomate seco.", 7690, None),
        ("Camarão", "Camarão refogado no alho, catupiry e salsinha.", 8490, None),
    ]),
    ("Pizzas doces", "pizza", [
        ("Chocolate com morango", "Chocolate ao leite derretido e morangos frescos fatiados.", 5890, "chocolate-morango.webp"),
        ("Brigadeiro", "Chocolate ao leite e granulado belga.", 5490, None),
        ("Romeu e Julieta", "Goiabada cremosa com mussarela e catupiry.", 5490, None),
        ("Banana com canela", "Banana fatiada, açúcar, canela e leite condensado.", 5290, None),
        ("Prestígio", "Chocolate ao leite e coco ralado.", 5690, None),
    ]),
    ("Bebidas", "bebida", [
        ("Coca-Cola lata 350 ml", "", 700, None),
        ("Guaraná Antarctica lata 350 ml", "", 650, None),
        ("Coca-Cola 2 litros", "", 1500, None),
        ("Guaraná Antarctica 2 litros", "", 1300, None),
        ("Suco de laranja natural", "Copo de 400 ml, espremido na hora.", 1100, None),
        ("Água mineral", "Garrafa de 500 ml, com ou sem gás.", 500, None),
        ("Heineken long neck", "", 1300, None),
        ("Chopp Brahma 300 ml", "", 1100, None),
    ]),
    ("Cafeteria", "outro", [
        ("Café espresso", "", 600, None),
        ("Cappuccino italiano", "Espresso, leite vaporizado e espuma.", 1100, None),
        ("Chocolate quente cremoso", "", 1200, None),
        ("Pão de queijo", "Porção com 6 unidades, saindo do forno.", 1400, None),
    ]),
    ("Sobremesas", "outro", [
        ("Petit gâteau", "Bolinho quente de chocolate com sorvete de creme.", 2400, None),
        ("Pudim de leite", "Fatia do pudim da casa.", 1300, None),
    ]),
]

BORDAS = [("Catupiry", 900), ("Cheddar", 900), ("Cream cheese", 1000), ("Chocolate", 1100)]
TOTAL_MESAS = 12
OBSERVACOES = ["Sem cebola", "Bem assada", "Sem azeitona", "Cortar em 12 fatias", "Pouco orégano"]


def popular_se_vazio(con):
    if con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]:
        return False
    popular(con)
    return True


def popular(con, semente=7):
    sorteio = random.Random(semente)
    with con:
        con.executemany(
            "INSERT INTO usuarios (nome, usuario, senha_hash, perfil) VALUES (?, ?, ?, ?)",
            [(nome, usuario, generate_password_hash(senha), perfil) for nome, usuario, senha, perfil in USUARIOS],
        )
        pizzas, bebidas, outros = [], [], []
        for ordem, (categoria, tipo, produtos) in enumerate(CARDAPIO, start=1):
            categoria_id = con.execute(
                "INSERT INTO categorias (nome, tipo, ordem) VALUES (?, ?, ?)", (categoria, tipo, ordem)
            ).lastrowid
            for nome, descricao, preco, foto in produtos:
                produto_id = con.execute(
                    "INSERT INTO produtos (categoria_id, nome, descricao, preco, imagem) VALUES (?, ?, ?, ?, ?)",
                    (categoria_id, nome, descricao, preco, FOTO + foto if foto else None),
                ).lastrowid
                {"pizza": pizzas, "bebida": bebidas, "outro": outros}[tipo].append((produto_id, nome, preco))
        bordas = [
            (con.execute("INSERT INTO bordas (nome, preco) VALUES (?, ?)", (nome, preco)).lastrowid, nome, preco)
            for nome, preco in BORDAS
        ]
        con.executemany("INSERT INTO mesas (numero) VALUES (?)", [(n,) for n in range(1, TOTAL_MESAS + 1)])
        _movimento(con, sorteio, pizzas, bebidas, outros, bordas)


def _fmt(momento):
    return momento.strftime("%Y-%m-%d %H:%M:%S")


def _itens_sorteados(sorteio, pizzas, bebidas, outros, bordas):
    """Sorteia itens com peso maior para os primeiros sabores, para o ranking ter líderes claros."""
    pesos = [max(1, 9 - posicao // 2) for posicao in range(len(pizzas))]
    itens = []
    for _ in range(sorteio.choice([1, 1, 2, 2, 3])):
        sabor = sorteio.choices(pizzas, pesos)[0]
        descricao, preco, sabor2_id, borda_id, detalhe = sabor[1], sabor[2], None, None, None
        if sorteio.random() < 0.3:
            outro = sorteio.choices(pizzas, pesos)[0]
            if outro[0] != sabor[0]:
                sabor2_id = outro[0]
                descricao = f"½ {sabor[1]} + ½ {outro[1]}"
                preco = max(sabor[2], outro[2])
        if sorteio.random() < 0.25:
            borda = sorteio.choice(bordas)
            borda_id, detalhe = borda[0], f"Borda {borda[1]}"
            preco += borda[2]
        observacao = sorteio.choice(OBSERVACOES) if sorteio.random() < 0.2 else None
        itens.append((sabor[0], sabor2_id, borda_id, descricao, detalhe, observacao, 1, preco))
    for bebida in sorteio.sample(bebidas, sorteio.choice([1, 2, 2, 3])):
        itens.append((bebida[0], None, None, bebida[1], None, None, sorteio.choice([1, 1, 2, 3]), bebida[2]))
    if sorteio.random() < 0.35:
        extra = sorteio.choice(outros)
        itens.append((extra[0], None, None, extra[1], None, None, sorteio.choice([1, 2]), extra[2]))
    return itens


def _inserir_pedido(con, comanda_id, mesa_id, status, momento, itens, origem, usuario_id):
    pedido_id = con.execute(
        """INSERT INTO pedidos (comanda_id, mesa_id, origem, usuario_id, status, criado_em, atualizado_em)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (comanda_id, mesa_id, origem, usuario_id, status, _fmt(momento), _fmt(momento)),
    ).lastrowid
    con.executemany(
        """INSERT INTO pedido_itens
           (pedido_id, produto_id, produto2_id, borda_id, descricao, detalhe, observacao, quantidade, preco_unit)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(pedido_id, *item) for item in itens],
    )
    return sum(item[6] * item[7] for item in itens)


def _conta_fechada(con, sorteio, catalogo, abertura, admin_id, garcom_id):
    mesa_id = sorteio.randint(1, TOTAL_MESAS)
    comanda_id = con.execute(
        "INSERT INTO comandas (mesa_id, status, aberta_em) VALUES (?, 'fechada', ?)", (mesa_id, _fmt(abertura))
    ).lastrowid
    origem = sorteio.choice(["cliente", "cliente", "garcom"])
    subtotal = _inserir_pedido(
        con, comanda_id, mesa_id, "entregue", abertura, _itens_sorteados(sorteio, *catalogo),
        origem, garcom_id if origem == "garcom" else None,
    )
    taxa_pct = sorteio.choice([10, 10, 10, 0])
    desconto = sorteio.choice([0, 0, 0, 0, 500])
    taxa = round(subtotal * taxa_pct / 100)
    total = subtotal - desconto + taxa
    fechamento = abertura + timedelta(minutes=sorteio.randint(35, 80))
    con.execute(
        """UPDATE comandas SET fechada_em = ?, subtotal = ?, desconto = ?, taxa_servico_pct = ?,
                  taxa_servico = ?, total = ?, fechada_por = ? WHERE id = ?""",
        (_fmt(fechamento), subtotal, desconto, taxa_pct, taxa, total, admin_id, comanda_id),
    )
    forma = sorteio.choices(["pix", "credito", "debito", "dinheiro"], [4, 3, 2, 1])[0]
    con.execute("INSERT INTO pagamentos (comanda_id, forma, valor) VALUES (?, ?, ?)", (comanda_id, forma, total))


def _movimento(con, sorteio, pizzas, bebidas, outros, bordas):
    catalogo = (pizzas, bebidas, outros, bordas)
    admin_id, garcom_id = 1, 2
    agora = datetime.now().replace(microsecond=0)

    # Seis dias anteriores, com o salão aberto das 18h às 23h.
    for dias in range(6, 0, -1):
        dia = (agora - timedelta(days=dias)).replace(hour=18, minute=0, second=0)
        for _ in range(sorteio.randint(9, 16)):
            _conta_fechada(con, sorteio, catalogo, dia + timedelta(minutes=sorteio.randint(0, 270)), admin_id, garcom_id)

    # Hoje: contas já fechadas nas últimas horas, sem passar para ontem nem para o futuro.
    inicio_do_dia = agora.replace(hour=0, minute=0, second=0)
    janela = max(1, min(int((agora - inicio_do_dia).total_seconds() // 60), 300))
    for _ in range(14):
        fechamento_max = agora - timedelta(minutes=sorteio.randint(1, janela))
        abertura = max(inicio_do_dia, fechamento_max - timedelta(minutes=90))
        _conta_fechada(con, sorteio, catalogo, abertura, admin_id, garcom_id)
    con.execute("UPDATE comandas SET fechada_em = ? WHERE fechada_em > ?", (_fmt(agora), _fmt(agora)))

    # Mesas abertas agora, com pedidos em cada etapa da cozinha.
    abertas = [(3, "entregue", 48), (7, "pronto", 21), (5, "preparo", 12), (9, "pendente", 4)]
    for mesa_id, status, minutos in abertas:
        momento = max(inicio_do_dia, agora - timedelta(minutes=minutos))
        comanda_id = con.execute(
            "INSERT INTO comandas (mesa_id, aberta_em) VALUES (?, ?)", (mesa_id, _fmt(momento))
        ).lastrowid
        _inserir_pedido(con, comanda_id, mesa_id, status, momento, _itens_sorteados(sorteio, *catalogo), "cliente", None)
    con.execute("UPDATE mesas SET chamado = 'conta', chamado_em = ? WHERE id = 3", (_fmt(agora - timedelta(minutes=2)),))
