# La Giovanna — cardápio digital e gestão da pizzaria

Sistema web para a Pizzaria e Cafeteria La Giovanna: o cliente pede pelo QR Code da mesa, o pedido cai na
tela da cozinha em tempo real, o garçom acompanha o salão pelo celular e a gerência fecha as contas e vê os
números do dia.

## Como rodar

Precisa de Python 3.10 ou mais novo.

```bash
python -m venv .venv
```

No Windows:

```bash
.venv\Scripts\activate
```

No Linux ou macOS:

```bash
source .venv/bin/activate
```

Depois:

```bash
pip install -r requirements.txt
```

```bash
python app.py
```

Abra <http://localhost:5000>. Na primeira vez o sistema cria o banco em `dados/lagiovanna.db` com o cardápio,
12 mesas, a equipe de teste e um movimento fictício para o painel já abrir com números.

- Outra porta: `python app.py --porta 8080`
- Zerar tudo e recriar a demonstração: `python app.py --reiniciar-demo`

### Usar com os celulares na pizzaria

O computador que roda o sistema e os celulares precisam estar na mesma rede Wi-Fi. Ao iniciar, o terminal
mostra o endereço da rede (algo como `http://192.168.0.10:5000`). Entre como gerente, abra
**Mesas e QR Codes**, salve esse endereço e imprima os QR Codes: cada um leva direto para `/mesa/05`, por exemplo.

## Acessos de teste

| Perfil  | Usuário   | Senha         | Tela       |
|---------|-----------|---------------|------------|
| Gerente | `admin`   | `giovanna123` | `/admin`   |
| Garçom  | `garcom`  | `garcom123`   | `/garcom`  |
| Cozinha | `cozinha` | `cozinha123`  | `/cozinha` |

O cliente não tem login: abre `/mesa/<número>` pelo QR Code. Troque as senhas em **Equipe** antes de usar de verdade.

## O que cada perfil faz

- **Cliente** (`/mesa/05`): cardápio por categoria, pizza inteira ou meio a meio (vale o preço do sabor mais
  caro), borda recheada, observações, envio para a cozinha, acompanhamento do pedido, chamar o garçom e pedir a conta.
- **Garçom**: mapa das mesas (livres, ocupadas, aguardando atendimento), aviso de pedido pronto, lançamento
  de pedidos pelo cliente e confirmação de entrega.
- **Cozinha**: fila em três colunas (pendentes, em preparo, prontos) por ordem de chegada, com a mesa em
  destaque, tempo de espera e aviso sonoro opcional.
- **Gerente**: resumo do dia (faturamento, ticket médio, pedidos, pizzas mais vendidas), caixa (consumo por
  mesa, estorno de item, desconto, taxa de serviço, formas de pagamento, fechamento), cardápio (produtos,
  categorias, bordas, fotos, pausar), mesas com QR Codes e equipe.

## Como é feito

- **Servidor**: Python, Flask e SQLite (arquivo único, sem instalar banco). Servido pelo Waitress.
- **Tempo real**: Server-Sent Events em `/api/eventos`; as telas recarregam os dados quando algo muda.
- **Telas**: Preact + htm, sem etapa de build. Os arquivos em `static/` são servidos como estão.
- **Segurança**: senhas com hash, sessão por cookie, permissões por perfil conferidas no servidor e preços
  sempre calculados no servidor.

```
app.py              inicia o servidor
lagiovanna/         servidor: banco (db), regras (servicos), rotas, admin, auth, eventos, seed
templates/          páginas HTML
static/             CSS, JavaScript, fontes e fotos
tests/              testes automáticos da API
```

Testes:

```bash
pip install pytest
```

```bash
python -m pytest
```
