import {
  html, useState, useEffect, useMemo, api, avisar, iniciar, useDados, useEventos, reais, mesa2, hora,
  paraCentavos, centavosParaTexto, semAcento, ROTULO_PAGAMENTO,
  Folha, ItensPedido, Selo, Letreiro, Icone,
} from './lib.js';

const USUARIO = window.DADOS.usuario;
const SECOES = [
  ['resumo', 'Resumo'], ['caixa', 'Caixa'], ['cardapio', 'Cardápio'], ['mesas', 'Mesas e QR Codes'], ['equipe', 'Equipe'],
  ['privacidade', 'Privacidade'],
];
const TIPO_CATEGORIA = { pizza: 'Pizza (meio a meio e borda)', bebida: 'Bebida', outro: 'Outros' };
const PERFIL = { admin: 'Gerente', garcom: 'Garçom', cozinha: 'Cozinha' };
const FORMAS = ['pix', 'credito', 'debito', 'dinheiro'];

// ---------- Peças de formulário ----------

function Interruptor({ ligado, aoMudar, rotulo }) {
  return html`<button type="button" role="switch" aria-checked=${ligado} aria-label=${rotulo}
    class="interruptor ${ligado ? 'ligado' : ''}" onClick=${() => aoMudar(!ligado)}>
    <span class="interruptor-pino"></span>
    <span class="interruptor-texto">${ligado ? 'Disponível' : 'Pausado'}</span>
  </button>`;
}

function CampoDinheiro({ valor, aoMudar, id, rotulo }) {
  const [texto, setTexto] = useState(centavosParaTexto(valor));
  useEffect(() => { if (paraCentavos(texto) !== valor) setTexto(centavosParaTexto(valor)); }, [valor]);
  return html`<span class="campo-dinheiro">
    <span aria-hidden="true">R$</span>
    <input id=${id} class="campo" inputmode="decimal" value=${texto} aria-label=${rotulo}
      onInput=${(e) => { setTexto(e.target.value); aoMudar(paraCentavos(e.target.value)); }}
      onBlur=${() => setTexto(centavosParaTexto(valor))} onFocus=${(e) => e.target.select()} />
  </span>`;
}

/** Reduz a foto no próprio navegador (até 900 px, JPEG) para o cardápio abrir rápido no celular. */
async function reduzirFoto(arquivo) {
  const imagem = await createImageBitmap(arquivo).catch(() => null);
  if (!imagem) throw new Error('Não consegui abrir essa imagem. Use JPG, PNG ou WebP.');
  const escala = Math.min(1, 900 / Math.max(imagem.width, imagem.height));
  const tela = document.createElement('canvas');
  tela.width = Math.round(imagem.width * escala);
  tela.height = Math.round(imagem.height * escala);
  const pincel = tela.getContext('2d');
  pincel.fillStyle = '#fff';
  pincel.fillRect(0, 0, tela.width, tela.height);
  pincel.drawImage(imagem, 0, 0, tela.width, tela.height);
  return new Promise((resolver) => tela.toBlob(resolver, 'image/jpeg', 0.85));
}

async function executar(acao, mensagem) {
  try {
    await acao();
    if (mensagem) avisar(mensagem);
    return true;
  } catch (e) {
    avisar(e.message, 'erro');
    return false;
  }
}

// ---------- Resumo ----------

function Barras({ titulo, dados, formatar, descricao }) {
  const maximo = Math.max(...dados.map((d) => d.valor), 1);
  const [aberta, setAberta] = useState(false);
  return html`<section class="painel">
    <header class="painel-topo">
      <h2>${titulo}</h2>
      <button class="link" onClick=${() => setAberta(!aberta)}>${aberta ? 'Ver gráfico' : 'Ver tabela'}</button>
    </header>
    ${dados.length === 0 && html`<p class="vazio">Ainda sem vendas neste dia.</p>`}
    ${dados.length > 0 && !aberta && html`<div class="barras" role="img" aria-label=${descricao}>
      ${dados.map((d) => html`<div key=${d.rotulo} class="barras-coluna ${d.valor === maximo ? 'maior' : ''}" tabindex="0">
        <span class="barras-valor">${formatar(d.valor)}</span>
        <span class="barras-trilho"><span class="barras-barra" style=${{ height: `${(d.valor / maximo) * 100}%` }}></span></span>
        <span class="barras-rotulo">${d.rotulo}</span>
      </div>`)}
    </div>`}
    ${dados.length > 0 && aberta && html`<table class="tabela tabela-compacta">
      <tbody>${dados.map((d) => html`<tr key=${d.rotulo}><th scope="row">${d.rotulo}</th><td class="num">${formatar(d.valor)}</td></tr>`)}</tbody>
    </table>`}
  </section>`;
}

function Ranking({ titulo, itens, formatar, vazio, posicoes = true }) {
  const maximo = Math.max(...itens.map((i) => i.valor), 1);
  return html`<section class="painel">
    <header class="painel-topo"><h2>${titulo}</h2></header>
    ${itens.length === 0 && html`<p class="vazio">${vazio}</p>`}
    <ol class="ranking ${posicoes ? '' : 'sem-posicao'}">
      ${itens.map((i, posicao) => html`<li key=${i.rotulo} title="${i.rotulo}: ${formatar(i.valor)}">
        ${posicoes && html`<span class="ranking-posicao">${posicao + 1}</span>`}
        <span class="ranking-nome">${i.rotulo}</span>
        <span class="ranking-valor">${formatar(i.valor)}</span>
        <span class="ranking-trilho"><span class="ranking-barra" style=${{ width: `${(i.valor / maximo) * 100}%` }}></span></span>
      </li>`)}
    </ol>
  </section>`;
}

function Resumo() {
  // Sem dia escolhido, o servidor responde com "hoje" no horário da pizzaria.
  const [dia, setDia] = useState('');
  const { dados, erro, recarregar } = useDados(`/api/admin/indicadores${dia ? `?dia=${dia}` : ''}`, ['pedidos', 'caixa']);
  const ehHoje = !dados || dados.dia === dados.hoje;
  const zerar = async () => {
    if (!confirm('Apagar TODAS as vendas (pedidos, contas e pagamentos) e liberar as mesas?\n\nO cardápio, as mesas e a equipe continuam. Isso não pode ser desfeito.')) return;
    if (await executar(() => api('/api/admin/zerar-vendas', { metodo: 'POST', corpo: { confirmacao: 'ZERAR' } }), 'Vendas zeradas. Tudo pronto para começar.')) recarregar();
  };
  const qtd = (n) => n.toLocaleString('pt-BR', { maximumFractionDigits: 1 });
  const diaCurto = (iso) => new Date(iso + 'T12:00').toLocaleDateString('pt-BR', { weekday: 'short', day: 'numeric' }).replace('.', '');

  return html`<div class="secao">
    <header class="secao-topo">
      <h1>${ehHoje ? 'Resumo de hoje' : 'Resumo do dia'}</h1>
      <label class="seletor-dia">Dia
        <input type="date" class="campo" value=${dia || dados?.dia || ''} max=${dados?.hoje}
          onChange=${(e) => e.target.value && setDia(e.target.value === dados?.hoje ? '' : e.target.value)} />
      </label>
    </header>
    ${!dados && html`<p class="carregando">${erro || 'Somando as vendas…'}</p>`}
    ${dados && html`
      <dl class="indicadores">
        <div class="indicador indicador-principal"><dt>Faturamento</dt><dd>${reais(dados.faturamento)}</dd>
          <p>${dados.contas_fechadas} ${dados.contas_fechadas === 1 ? 'conta fechada' : 'contas fechadas'}</p></div>
        <div class="indicador"><dt>Ticket médio</dt><dd>${reais(dados.ticket_medio)}</dd><p>por conta fechada</p></div>
        <div class="indicador"><dt>Pedidos</dt><dd>${dados.pedidos}</dd><p>enviados à cozinha</p></div>
        ${ehHoje && html`<div class="indicador"><dt>Em aberto</dt><dd>${reais(dados.em_aberto)}</dd>
          <p>${dados.mesas_abertas} ${dados.mesas_abertas === 1 ? 'mesa ocupada' : 'mesas ocupadas'} agora</p></div>`}
      </dl>
      <div class="paineis">
        <${Barras} titulo="Vendas por hora" formatar=${reais} descricao="Valor vendido em cada hora do dia"
          dados=${dados.vendas_por_hora.map((v) => ({ rotulo: `${v.hora}h`, valor: v.valor }))} />
        <${Ranking} titulo="Pizzas mais vendidas" formatar=${qtd} vazio="Nenhuma pizza vendida neste dia."
          itens=${dados.ranking_pizzas.map((r) => ({ rotulo: r.nome, valor: r.quantidade }))} />
        <${Barras} titulo="Faturamento nos últimos 7 dias" formatar=${reais} descricao="Faturamento de cada um dos últimos sete dias"
          dados=${dados.ultimos_dias.map((d) => ({ rotulo: diaCurto(d.dia), valor: d.valor }))} />
        <${Ranking} titulo="Formas de pagamento" posicoes=${false} formatar=${reais} vazio="Nenhuma conta fechada neste dia."
          itens=${dados.pagamentos.filter((p) => p.valor > 0).sort((a, b) => b.valor - a.valor)
            .map((p) => ({ rotulo: ROTULO_PAGAMENTO[p.forma], valor: p.valor }))} />
      </div>
      <p class="zerar">Fez testes e quer recomeçar do zero?${' '}
        <button class="link" onClick=${zerar}>Zerar todas as vendas</button></p>`}
  </div>`;
}

// ---------- Caixa ----------

function Conta({ mesaId, aoFechar }) {
  const { dados: mesa, recarregar } = useDados(`/api/mesas/${mesaId}`, ['pedidos', 'mesas']);
  const [desconto, setDesconto] = useState(0);
  const [comTaxa, setComTaxa] = useState(true);
  const [taxaPct, setTaxaPct] = useState(10);
  const [pagamentos, setPagamentos] = useState([]);
  const [entregue, setEntregue] = useState(0);
  const [fechando, setFechando] = useState(false);

  if (!mesa) return html`<section class="conta"><p class="carregando">Abrindo a conta…</p></section>`;
  if (!mesa.comanda_id) return html`<section class="conta"><p class="vazio">Esta mesa não tem conta aberta.</p></section>`;

  const pct = comTaxa ? taxaPct : 0;
  const taxa = Math.round(mesa.subtotal * pct / 100);
  const total = mesa.subtotal - Math.min(desconto, mesa.subtotal) + taxa;
  const pago = pagamentos.reduce((soma, p) => soma + p.valor, 0);
  const falta = total - pago;
  const emDinheiro = pagamentos.filter((p) => p.forma === 'dinheiro').reduce((s, p) => s + p.valor, 0);
  const naCozinha = mesa.pedidos.filter((p) => ['pendente', 'preparo'].includes(p.status)).length;

  const pagarCom = (forma) => {
    if (falta <= 0) return avisar('A conta já está toda paga. Ajuste os valores para dividir.', 'erro');
    setPagamentos([...pagamentos, { forma, valor: falta, id: Date.now() }]);
  };
  const mudarPagamento = (id, valor) => setPagamentos(pagamentos.map((p) => (p.id === id ? { ...p, valor } : p)));

  const estornar = async (item) => {
    if (!confirm(`Tirar "${item.descricao}" da conta?`)) return;
    if (await executar(() => api(`/api/admin/itens/${item.id}`, { metodo: 'DELETE' }), 'Item tirado da conta')) recarregar();
  };

  const fechar = async () => {
    setFechando(true);
    const ok = await executar(() => api(`/api/admin/mesas/${mesaId}/fechar`, {
      metodo: 'POST',
      corpo: {
        desconto: Math.min(desconto, mesa.subtotal),
        taxa_servico_pct: pct,
        pagamentos: pagamentos.filter((p) => p.valor > 0).map(({ forma, valor }) => ({ forma, valor })),
      },
    }), `Conta da mesa ${mesa2(mesa.numero)} fechada. Mesa liberada.`);
    setFechando(false);
    if (ok) aoFechar();
  };

  return html`<section class="conta" aria-label="Conta da mesa ${mesa2(mesa.numero)}">
    <header class="conta-topo">
      <h2>Mesa ${mesa2(mesa.numero)}</h2>
      <p>Aberta às ${hora(mesa.aberta_em)}${mesa.chamado === 'conta' ? ', pediu a conta' : ''}</p>
    </header>
    ${naCozinha > 0 && html`<p class="aviso aviso-atencao">Ainda ${naCozinha === 1 ? 'há 1 pedido' : `há ${naCozinha} pedidos`} na cozinha para esta mesa.</p>`}

    <div class="conta-itens">
      ${mesa.pedidos.map((p) => html`<div key=${p.id} class="conta-pedido ${p.status === 'cancelado' ? 'cancelado' : ''}">
        <p class="conta-pedido-topo">Pedido das ${hora(p.criado_em)} <${Selo} status=${p.status} /></p>
        <ul>
          ${p.itens.map((i) => html`<li key=${i.id} class=${i.cancelado || p.status === 'cancelado' ? 'cancelado' : ''}>
            <span class="item-qtd">${i.quantidade}×</span>
            <span class="item-texto"><span class="item-nome">${i.descricao}</span>
              ${i.detalhe && html`<span class="item-detalhe">${i.detalhe}</span>`}</span>
            <span class="num">${reais(i.quantidade * i.preco_unit)}</span>
            ${!i.cancelado && p.status !== 'cancelado'
              ? html`<button class="botao-icone botao-perigo" aria-label="Tirar ${i.descricao} da conta" title="Tirar da conta"
                  onClick=${() => estornar(i)}><${Icone} nome="lixeira" tamanho=${18} /></button>`
              : html`<span class="estornado">tirado</span>`}
          </li>`)}
        </ul>
      </div>`)}
    </div>

    <div class="conta-soma">
      <p><span>Consumo</span><span class="num">${reais(mesa.subtotal)}</span></p>
      <p><label for="desconto">Desconto</label>
        <${CampoDinheiro} id="desconto" valor=${desconto} aoMudar=${setDesconto} rotulo="Desconto em reais" /></p>
      <p><label class="marcar"><input type="checkbox" checked=${comTaxa} onChange=${(e) => setComTaxa(e.target.checked)} />
          Taxa de serviço</label>
        <span class="taxa">
          <input class="campo campo-curto" type="number" min="0" max="30" step="1" value=${taxaPct} disabled=${!comTaxa}
            aria-label="Percentual da taxa de serviço" onInput=${(e) => setTaxaPct(Math.min(30, Math.max(0, Number(e.target.value) || 0)))} />
          <span>%</span><span class="num">${reais(taxa)}</span>
        </span></p>
      <p class="conta-total"><span>Total</span><span class="num">${reais(total)}</span></p>
    </div>

    <div class="conta-pagamento">
      <h3>Como o cliente vai pagar?</h3>
      <div class="formas">
        ${FORMAS.map((f) => html`<button key=${f} class="botao botao-contorno" onClick=${() => pagarCom(f)}>${ROTULO_PAGAMENTO[f]}</button>`)}
      </div>
      ${pagamentos.map((p) => html`<p key=${p.id} class="pagamento">
        <span>${ROTULO_PAGAMENTO[p.forma]}</span>
        <${CampoDinheiro} valor=${p.valor} aoMudar=${(v) => mudarPagamento(p.id, v)} rotulo="Valor em ${ROTULO_PAGAMENTO[p.forma]}" />
        <button class="botao-icone" aria-label="Tirar pagamento em ${ROTULO_PAGAMENTO[p.forma]}"
          onClick=${() => setPagamentos(pagamentos.filter((x) => x.id !== p.id))}><${Icone} nome="fechar" tamanho=${18} /></button>
      </p>`)}
      ${emDinheiro > 0 && html`<p class="pagamento troco">
        <label for="entregue">Cliente entregou</label>
        <${CampoDinheiro} id="entregue" valor=${entregue} aoMudar=${setEntregue} rotulo="Valor entregue em dinheiro" />
        <span class="num">${entregue > emDinheiro ? `Troco ${reais(entregue - emDinheiro)}` : 'Sem troco'}</span>
      </p>`}
      <p class="conferencia ${falta === 0 ? 'certa' : ''}" role="status">
        ${falta === 0 ? html`<${Icone} nome="check" tamanho=${18} /> Pagamento confere com o total`
          : falta > 0 ? `Falta receber ${reais(falta)}` : `Os pagamentos passam ${reais(-falta)} do total`}
      </p>
      <button class="botao botao-primario botao-largo" disabled=${falta !== 0 || fechando} onClick=${fechar}>
        ${fechando ? 'Fechando…' : 'Fechar conta e liberar a mesa'}
      </button>
    </div>
  </section>`;
}

function Caixa() {
  const mesas = useDados('/api/mesas', ['pedidos', 'mesas']);
  const contas = useDados('/api/admin/contas', ['caixa']);
  const [mesaId, setMesaId] = useState(null);
  const abertas = (mesas.dados || []).filter((m) => m.comanda_id);
  const livres = (mesas.dados || []).length - abertas.length;
  const selecionada = abertas.find((m) => m.id === mesaId);

  return html`<div class="secao">
    <header class="secao-topo"><h1>Caixa</h1><p>${abertas.length} ${abertas.length === 1 ? 'mesa com conta aberta' : 'mesas com conta aberta'}, ${livres} livres</p></header>
    <div class="caixa">
      <nav class="caixa-mesas" aria-label="Mesas com conta aberta">
        ${!mesas.dados && html`<p class="carregando">Carregando as mesas…</p>`}
        ${mesas.dados && abertas.length === 0 && html`<p class="vazio">Nenhuma conta aberta agora. Quando um pedido chegar, a mesa aparece aqui.</p>`}
        ${abertas.map((m) => html`<button key=${m.id} class="caixa-mesa ${m.id === mesaId ? 'ativa' : ''}" onClick=${() => setMesaId(m.id)}>
          <span class="caixa-mesa-numero">${mesa2(m.numero)}</span>
          <span class="caixa-mesa-texto">
            <strong>${reais(m.subtotal)}</strong>
            <small>${m.chamado === 'conta' ? 'Pediu a conta' : `desde ${hora(m.aberta_em)}`}</small>
          </span>
          ${m.chamado === 'conta' && html`<span class="selo selo-pronto">Conta</span>`}
        </button>`)}
      </nav>
      ${selecionada
        ? html`<${Conta} key=${selecionada.id} mesaId=${selecionada.id} aoFechar=${() => { setMesaId(null); mesas.recarregar(); contas.recarregar(); }} />`
        : html`<section class="conta conta-vazia"><p>Escolha uma mesa para ver o consumo e fechar a conta.</p></section>`}
    </div>

    <section class="painel">
      <header class="painel-topo"><h2>Contas fechadas hoje</h2></header>
      ${contas.dados && contas.dados.length === 0 && html`<p class="vazio">Nenhuma conta fechada hoje.</p>`}
      ${contas.dados && contas.dados.length > 0 && html`<div class="tabela-rolagem"><table class="tabela">
        <thead><tr><th>Hora</th><th>Mesa</th><th class="num">Consumo</th><th class="num">Desconto</th><th class="num">Serviço</th><th class="num">Total</th><th>Pagamento</th></tr></thead>
        <tbody>${contas.dados.map((c) => html`<tr key=${c.id}>
          <td>${hora(c.fechada_em)}</td><td>${mesa2(c.mesa)}</td>
          <td class="num">${reais(c.subtotal)}</td><td class="num">${c.desconto ? reais(c.desconto) : ''}</td>
          <td class="num">${c.taxa_servico ? reais(c.taxa_servico) : ''}</td><td class="num"><strong>${reais(c.total)}</strong></td>
          <td>${c.pagamentos.map((p) => ROTULO_PAGAMENTO[p.forma]).join(' + ')}</td>
        </tr>`)}</tbody>
      </table></div>`}
    </section>
  </div>`;
}

// ---------- Cardápio ----------

function FormularioProduto({ produto, categorias, aoSalvar, aoFechar }) {
  const [f, setF] = useState(() => ({
    nome: '', descricao: '', preco: 0, imagem: null, ativo: true, categoria_id: categorias[0]?.id, ...produto,
  }));
  const [enviando, setEnviando] = useState(false);
  const campo = (nome) => (e) => setF({ ...f, [nome]: e.target.value });

  const enviarFoto = async (e) => {
    const arquivo = e.target.files[0];
    if (!arquivo) return;
    setEnviando(true);
    try {
      const form = new FormData();
      form.append('imagem', await reduzirFoto(arquivo), 'foto.jpg');
      const { url } = await api('/api/admin/upload', { metodo: 'POST', form });
      setF((atual) => ({ ...atual, imagem: url }));
    } catch (erro) { avisar(erro.message, 'erro'); }
    setEnviando(false);
    e.target.value = '';
  };

  const salvar = async (e) => {
    e.preventDefault();
    const corpo = { ...f, categoria_id: Number(f.categoria_id), ativo: !!f.ativo };
    const ok = await executar(
      () => api(produto?.id ? `/api/admin/produtos/${produto.id}` : '/api/admin/produtos', { metodo: produto?.id ? 'PUT' : 'POST', corpo }),
      produto?.id ? 'Produto salvo' : 'Produto criado',
    );
    if (ok) aoSalvar();
  };

  return html`<${Folha} titulo=${produto?.id ? 'Editar produto' : 'Novo produto'} aoFechar=${aoFechar}>
    <form class="formulario" onSubmit=${salvar}>
      <label class="rotulo" for="p-nome">Nome</label>
      <input id="p-nome" class="campo" value=${f.nome} onInput=${campo('nome')} maxlength="60" required />
      <div class="formulario-dupla">
        <div><label class="rotulo" for="p-cat">Categoria</label>
          <select id="p-cat" class="campo" value=${f.categoria_id} onChange=${campo('categoria_id')}>
            ${categorias.map((c) => html`<option key=${c.id} value=${c.id}>${c.nome}</option>`)}
          </select></div>
        <div><label class="rotulo" for="p-preco">Preço</label>
          <${CampoDinheiro} id="p-preco" valor=${f.preco} aoMudar=${(preco) => setF((a) => ({ ...a, preco }))} rotulo="Preço" /></div>
      </div>
      <label class="rotulo" for="p-desc">Descrição</label>
      <textarea id="p-desc" class="campo" rows="2" maxlength="240" value=${f.descricao} onInput=${campo('descricao')}
        placeholder="Ingredientes ou tamanho"></textarea>
      <span class="rotulo">Foto</span>
      <div class="foto-campo">
        ${f.imagem ? html`<img src=${f.imagem} alt="Foto atual" />` : html`<span class="foto-vazia">Sem foto</span>`}
        <div>
          <label class="botao botao-contorno">${enviando ? 'Enviando…' : f.imagem ? 'Trocar foto' : 'Escolher foto'}
            <input type="file" accept="image/png,image/jpeg,image/webp" class="escondido" onChange=${enviarFoto} disabled=${enviando} /></label>
          ${f.imagem && html`<button type="button" class="botao botao-fantasma" onClick=${() => setF({ ...f, imagem: null })}>Tirar foto</button>`}
        </div>
      </div>
      <label class="marcar"><input type="checkbox" checked=${!!f.ativo} onChange=${(e) => setF({ ...f, ativo: e.target.checked })} />
        Disponível no cardápio</label>
      <button class="botao botao-primario botao-largo" disabled=${enviando}>Salvar produto</button>
    </form>
  <//>`;
}

function FormularioSimples({ titulo, registro, caminho, comPreco, comTipo, aoSalvar, aoFechar }) {
  const [f, setF] = useState(() => ({ nome: '', preco: 0, tipo: 'outro', ativo: true, ...registro }));
  const salvar = async (e) => {
    e.preventDefault();
    const ok = await executar(
      () => api(registro?.id ? `${caminho}/${registro.id}` : caminho, { metodo: registro?.id ? 'PUT' : 'POST', corpo: f }),
      'Salvo',
    );
    if (ok) aoSalvar();
  };
  return html`<${Folha} titulo=${titulo} aoFechar=${aoFechar}>
    <form class="formulario" onSubmit=${salvar}>
      <label class="rotulo" for="s-nome">Nome</label>
      <input id="s-nome" class="campo" value=${f.nome} onInput=${(e) => setF({ ...f, nome: e.target.value })} maxlength="60" required />
      ${comPreco && html`<label class="rotulo" for="s-preco">Preço a mais na pizza</label>
        <${CampoDinheiro} id="s-preco" valor=${f.preco} aoMudar=${(preco) => setF((a) => ({ ...a, preco }))} rotulo="Preço" />`}
      ${comTipo && html`<label class="rotulo" for="s-tipo">Tipo de item</label>
        <select id="s-tipo" class="campo" value=${f.tipo} onChange=${(e) => setF({ ...f, tipo: e.target.value })}>
          ${Object.entries(TIPO_CATEGORIA).map(([valor, rotulo]) => html`<option key=${valor} value=${valor}>${rotulo}</option>`)}
        </select>`}
      <button class="botao botao-primario botao-largo">Salvar</button>
    </form>
  <//>`;
}

function CardapioAdmin() {
  const { dados, erro, recarregar } = useDados('/api/admin/cardapio', ['cardapio']);
  const [aba, setAba] = useState('produtos');
  const [editando, setEditando] = useState(null);
  const [termo, setTermo] = useState('');
  const [filtroCategoria, setFiltroCategoria] = useState('');

  if (!dados) return html`<div class="secao"><p class="carregando">${erro || 'Abrindo o cardápio…'}</p></div>`;
  const fecharFormulario = () => { setEditando(null); recarregar(); };

  const alternar = async (tabela, registro, ativo) => {
    if (await executar(() => api(`/api/admin/${tabela}/${registro.id}/ativo`, { metodo: 'POST', corpo: { ativo } }),
      ativo ? `${registro.nome} voltou ao cardápio` : `${registro.nome} pausado`)) recarregar();
  };
  const excluir = async (tabela, registro) => {
    if (!confirm(`Excluir "${registro.nome}"? Isso não pode ser desfeito.`)) return;
    if (await executar(() => api(`/api/admin/${tabela}/${registro.id}`, { metodo: 'DELETE' }), `${registro.nome} excluído`)) recarregar();
  };
  const mover = async (indice, passo) => {
    const ids = dados.categorias.map((c) => c.id);
    const destino = indice + passo;
    if (destino < 0 || destino >= ids.length) return;
    [ids[indice], ids[destino]] = [ids[destino], ids[indice]];
    if (await executar(() => api('/api/admin/categorias/ordem', { metodo: 'POST', corpo: { ids } }))) recarregar();
  };

  const alvo = semAcento(termo.trim());
  const grupos = dados.categorias
    .filter((c) => !filtroCategoria || String(c.id) === filtroCategoria)
    .map((c) => ({ ...c, produtos: dados.produtos.filter((p) => p.categoria_id === c.id && (!alvo || semAcento(p.nome).includes(alvo))) }))
    .filter((c) => c.produtos.length || (!alvo && filtroCategoria));
  const acoes = (tabela, registro, tipo) => html`<td class="acoes">
    <button class="botao-icone" aria-label="Editar ${registro.nome}" title="Editar" onClick=${() => setEditando({ tipo, registro })}><${Icone} nome="lapis" tamanho=${18} /></button>
    <button class="botao-icone botao-perigo" aria-label="Excluir ${registro.nome}" title="Excluir" onClick=${() => excluir(tabela, registro)}><${Icone} nome="lixeira" tamanho=${18} /></button>
  </td>`;

  return html`<div class="secao">
    <header class="secao-topo">
      <h1>Cardápio</h1>
      <button class="botao botao-primario" onClick=${() => setEditando({ tipo: aba === 'produtos' ? 'produto' : aba === 'categorias' ? 'categoria' : 'borda' })}>
        <${Icone} nome="mais" tamanho=${18} /> ${aba === 'produtos' ? 'Novo produto' : aba === 'categorias' ? 'Nova categoria' : 'Nova borda'}
      </button>
    </header>
    <div class="abas" role="tablist">
      ${[['produtos', `Produtos (${dados.produtos.length})`], ['categorias', `Categorias (${dados.categorias.length})`], ['bordas', `Bordas (${dados.bordas.length})`]]
        .map(([valor, rotulo]) => html`<button key=${valor} role="tab" aria-selected=${aba === valor} class=${aba === valor ? 'ativa' : ''}
          onClick=${() => setAba(valor)}>${rotulo}</button>`)}
    </div>

    ${aba === 'produtos' && html`
      <div class="filtros-cardapio">
        <label class="busca"><${Icone} nome="busca" tamanho=${18} />
          <input type="search" placeholder="Buscar produto" value=${termo} onInput=${(e) => setTermo(e.target.value)} aria-label="Buscar produto" /></label>
        <select class="campo" value=${filtroCategoria} onChange=${(e) => setFiltroCategoria(e.target.value)} aria-label="Filtrar por categoria">
          <option value="">Todas as categorias</option>
          ${dados.categorias.map((c) => html`<option key=${c.id} value=${c.id}>${c.nome}</option>`)}
        </select>
      </div>
      ${grupos.length === 0 && html`<p class="vazio">Nenhum produto encontrado.</p>`}
      ${grupos.map((c) => html`<section key=${c.id} class="painel">
        <header class="painel-topo"><h2>${c.nome}</h2>${!c.ativo && html`<span class="selo selo-cancelado">Categoria pausada</span>`}</header>
        ${c.produtos.length === 0 && html`<p class="vazio">Categoria sem produtos.</p>`}
        <div class="tabela-rolagem"><table class="tabela tabela-produtos"><tbody>
          ${c.produtos.map((p) => html`<tr key=${p.id} class=${p.ativo ? '' : 'pausado'}>
            <td class="celula-foto">${p.imagem ? html`<img src=${p.imagem} alt="" loading="lazy" />` : html`<span class="foto-vazia" aria-hidden="true"></span>`}</td>
            <td><strong>${p.nome}</strong><small>${p.descricao}</small></td>
            <td class="num">${reais(p.preco)}</td>
            <td><${Interruptor} ligado=${!!p.ativo} rotulo="${p.nome} disponível" aoMudar=${(v) => alternar('produtos', p, v)} /></td>
            ${acoes('produtos', p, 'produto')}
          </tr>`)}
        </tbody></table></div>
      </section>`)}`}

    ${aba === 'categorias' && html`<section class="painel"><div class="tabela-rolagem"><table class="tabela"><tbody>
      ${dados.categorias.map((c, i) => html`<tr key=${c.id} class=${c.ativo ? '' : 'pausado'}>
        <td class="acoes">
          <button class="botao-icone" aria-label="Subir ${c.nome}" disabled=${i === 0} onClick=${() => mover(i, -1)}><${Icone} nome="cima" tamanho=${18} /></button>
          <button class="botao-icone" aria-label="Descer ${c.nome}" disabled=${i === dados.categorias.length - 1} onClick=${() => mover(i, 1)}><${Icone} nome="baixo" tamanho=${18} /></button>
        </td>
        <td><strong>${c.nome}</strong><small>${TIPO_CATEGORIA[c.tipo]}, ${dados.produtos.filter((p) => p.categoria_id === c.id).length} produtos</small></td>
        <td><${Interruptor} ligado=${!!c.ativo} rotulo="${c.nome} disponível" aoMudar=${(v) => alternar('categorias', c, v)} /></td>
        ${acoes('categorias', c, 'categoria')}
      </tr>`)}
    </tbody></table></div></section>`}

    ${aba === 'bordas' && html`<section class="painel">
      ${dados.bordas.length === 0 && html`<p class="vazio">Nenhuma borda cadastrada.</p>`}
      <div class="tabela-rolagem"><table class="tabela"><tbody>
      ${dados.bordas.map((b) => html`<tr key=${b.id} class=${b.ativo ? '' : 'pausado'}>
        <td><strong>Borda ${b.nome}</strong></td>
        <td class="num">+ ${reais(b.preco)}</td>
        <td><${Interruptor} ligado=${!!b.ativo} rotulo="Borda ${b.nome} disponível" aoMudar=${(v) => alternar('bordas', b, v)} /></td>
        ${acoes('bordas', b, 'borda')}
      </tr>`)}
    </tbody></table></div></section>`}

    ${editando?.tipo === 'produto' && html`<${FormularioProduto} produto=${editando.registro} categorias=${dados.categorias}
      aoSalvar=${fecharFormulario} aoFechar=${() => setEditando(null)} />`}
    ${editando?.tipo === 'categoria' && html`<${FormularioSimples} titulo=${editando.registro ? 'Editar categoria' : 'Nova categoria'}
      registro=${editando.registro} caminho="/api/admin/categorias" comTipo=${true} aoSalvar=${fecharFormulario} aoFechar=${() => setEditando(null)} />`}
    ${editando?.tipo === 'borda' && html`<${FormularioSimples} titulo=${editando.registro ? 'Editar borda' : 'Nova borda'}
      registro=${editando.registro} caminho="/api/admin/bordas" comPreco=${true} aoSalvar=${fecharFormulario} aoFechar=${() => setEditando(null)} />`}
  </div>`;
}

// ---------- Mesas e QR Codes ----------

function Mesas() {
  const { dados, erro, recarregar } = useDados('/api/admin/mesas', ['mesas']);
  const [numero, setNumero] = useState('');
  const [endereco, setEndereco] = useState(null);

  if (!dados) return html`<div class="secao"><p class="carregando">${erro || 'Carregando as mesas…'}</p></div>`;
  const local = /\/\/(localhost|127\.)/.test(dados.url_base);
  const proximo = dados.mesas.length ? Math.max(...dados.mesas.map((m) => m.numero)) + 1 : 1;

  const salvarEndereco = async (valor) => {
    if (await executar(() => api('/api/admin/config/url_base', { metodo: 'PUT', corpo: { url_base: valor } }), 'Endereço salvo. QR Codes atualizados.')) {
      setEndereco(null);
      recarregar();
    }
  };
  const adicionar = async (e) => {
    e.preventDefault();
    const n = parseInt(numero || proximo, 10);
    if (await executar(() => api('/api/admin/mesas', { metodo: 'POST', corpo: { numero: n } }), `Mesa ${mesa2(n)} criada`)) {
      setNumero('');
      recarregar();
    }
  };
  const excluir = async (m) => {
    if (!confirm(`Excluir a mesa ${mesa2(m.numero)}? O QR Code dela deixa de funcionar.`)) return;
    if (await executar(() => api(`/api/admin/mesas/${m.id}`, { metodo: 'DELETE' }), `Mesa ${mesa2(m.numero)} excluída`)) recarregar();
  };
  const trocarCodigo = async (m) => {
    if (!confirm(`Trocar o código da mesa ${mesa2(m.numero)}?\n\nO QR Code impresso hoje para de aceitar pedidos e você precisa imprimir o novo. Use isto se o QR Code foi fotografado ou levado da mesa.`)) return;
    if (await executar(() => api(`/api/admin/mesas/${m.id}/novo-codigo`, { metodo: 'POST' }), `Código da mesa ${mesa2(m.numero)} trocado. Imprima o QR Code novo.`)) recarregar();
  };
  const copiar = async (link) => {
    try { await navigator.clipboard.writeText(link); avisar('Link copiado'); }
    catch { prompt('Copie o link da mesa:', link); }
  };

  return html`<div class="secao">
    <header class="secao-topo">
      <h1>Mesas e QR Codes</h1>
      <a class="botao botao-primario" href="/admin/qrcodes" target="_blank" rel="noopener">Imprimir todos os QR Codes</a>
    </header>

    <section class="painel endereco">
      <header class="painel-topo"><h2>Endereço que vai dentro dos QR Codes</h2></header>
      <form class="endereco-form" onSubmit=${(e) => { e.preventDefault(); salvarEndereco(endereco ?? dados.url_base); }}>
        <input class="campo" value=${endereco ?? dados.url_base} onInput=${(e) => setEndereco(e.target.value)}
          aria-label="Endereço do sistema" placeholder="http://192.168.0.10:5000" spellcheck=${false} />
        <button class="botao botao-contorno" disabled=${endereco === null || endereco === dados.url_base}>Salvar endereço</button>
      </form>
      ${local && html`<p class="aviso aviso-atencao">O celular do cliente não consegue abrir “localhost”.
        ${dados.sugestao_rede
          ? html` Use o endereço deste computador na rede Wi-Fi: <button class="link" onClick=${() => salvarEndereco(dados.sugestao_rede)}>usar ${dados.sugestao_rede}</button>`
          : ' Informe o endereço deste computador na rede Wi-Fi ou o domínio do site.'}</p>`}
    </section>

    <form class="nova-mesa" onSubmit=${adicionar}>
      <label for="nova-mesa">Nova mesa número</label>
      <input id="nova-mesa" class="campo campo-curto" inputmode="numeric" value=${numero} placeholder=${proximo}
        onInput=${(e) => setNumero(e.target.value.replace(/\D/g, '').slice(0, 3))} />
      <button class="botao botao-contorno">Adicionar mesa</button>
    </form>

    ${dados.mesas.length === 0 && html`<p class="vazio">Nenhuma mesa cadastrada. Adicione a primeira acima.</p>`}
    <ul class="placas">
      ${dados.mesas.map((m) => html`<li key=${m.id} class="placa">
        <img src="/api/admin/mesas/${m.id}/qr.svg?e=${encodeURIComponent(m.link)}" alt="QR Code da mesa ${mesa2(m.numero)}" width="150" height="150" loading="lazy" />
        <div class="placa-texto">
          <h2>Mesa ${mesa2(m.numero)}</h2>
          <a href=${m.link} target="_blank" rel="noopener">${m.link.replace(/^https?:\/\//, '').replace(/\?c=.*/, '')}</a>
          <div class="placa-acoes">
            <button class="botao botao-fantasma" onClick=${() => copiar(m.link)}><${Icone} nome="copiar" tamanho=${16} /> Copiar link</button>
            <a class="botao botao-fantasma" href="/api/admin/mesas/${m.id}/qr.svg?baixar=1">Baixar QR</a>
            <button class="botao botao-fantasma" onClick=${() => trocarCodigo(m)}>Trocar código</button>
            <button class="botao botao-fantasma botao-perigo" onClick=${() => excluir(m)}>Excluir</button>
          </div>
        </div>
      </li>`)}
    </ul>
  </div>`;
}

// ---------- Equipe ----------

function FormularioPessoa({ pessoa, aoSalvar, aoFechar }) {
  const [f, setF] = useState(() => ({ nome: '', usuario: '', senha: '', perfil: 'garcom', ativo: true, ...pessoa }));
  const campo = (nome) => (e) => setF({ ...f, [nome]: e.target.value });
  const salvar = async (e) => {
    e.preventDefault();
    const ok = await executar(
      () => api(pessoa ? `/api/admin/usuarios/${pessoa.id}` : '/api/admin/usuarios', { metodo: pessoa ? 'PUT' : 'POST', corpo: { ...f, ativo: !!f.ativo } }),
      pessoa ? 'Dados salvos' : `${f.nome} já pode entrar`,
    );
    if (ok) aoSalvar();
  };
  return html`<${Folha} titulo=${pessoa ? `Editar ${pessoa.nome}` : 'Nova pessoa na equipe'} aoFechar=${aoFechar}>
    <form class="formulario" onSubmit=${salvar}>
      <label class="rotulo" for="u-nome">Nome</label>
      <input id="u-nome" class="campo" value=${f.nome} onInput=${campo('nome')} maxlength="60" required />
      ${!pessoa && html`<label class="rotulo" for="u-usuario">Usuário para entrar</label>
        <input id="u-usuario" class="campo" value=${f.usuario} onInput=${campo('usuario')} autocapitalize="none" spellcheck=${false}
          pattern="[a-z0-9._\\-]{3,30}" title="3 a 30 letras minúsculas, números, ponto ou hífen" required />`}
      <label class="rotulo" for="u-perfil">Função</label>
      <select id="u-perfil" class="campo" value=${f.perfil} onChange=${campo('perfil')}>
        ${Object.entries(PERFIL).map(([valor, rotulo]) => html`<option key=${valor} value=${valor}>${rotulo}</option>`)}
      </select>
      <label class="rotulo" for="u-senha">${pessoa ? 'Senha provisória nova (deixe em branco para manter)' : 'Senha provisória (8 caracteres ou mais)'}</label>
      <input id="u-senha" class="campo" type="password" value=${f.senha} onInput=${campo('senha')} minlength="8"
        required=${!pessoa} autocomplete="new-password" />
      <p class="grupo-nota">A pessoa cria a própria senha no primeiro acesso.</p>
      ${pessoa && html`<label class="marcar"><input type="checkbox" checked=${!!f.ativo} onChange=${(e) => setF({ ...f, ativo: e.target.checked })} />
        Pode entrar no sistema</label>`}
      <button class="botao botao-primario botao-largo">Salvar</button>
    </form>
  <//>`;
}

function Equipe() {
  const { dados, erro, recarregar } = useDados('/api/admin/usuarios');
  const [editando, setEditando] = useState(null);
  if (!dados) return html`<div class="secao"><p class="carregando">${erro || 'Carregando a equipe…'}</p></div>`;
  const excluir = async (u) => {
    if (!confirm(`Excluir ${u.nome} da equipe?\n\nO nome e o usuário são apagados e o acesso é encerrado. As vendas que essa pessoa registrou continuam, sem o nome.`)) return;
    if (await executar(() => api(`/api/admin/usuarios/${u.id}`, { metodo: 'DELETE' }), `${u.nome} excluído da equipe`)) recarregar();
  };
  return html`<div class="secao">
    <header class="secao-topo">
      <h1>Equipe</h1>
      <button class="botao botao-primario" onClick=${() => setEditando({})}><${Icone} nome="mais" tamanho=${18} /> Nova pessoa</button>
    </header>
    <section class="painel"><div class="tabela-rolagem"><table class="tabela">
      <thead><tr><th>Nome</th><th>Usuário</th><th>Função</th><th>Acesso</th><th></th></tr></thead>
      <tbody>${dados.map((u) => html`<tr key=${u.id} class=${u.ativo ? '' : 'pausado'}>
        <td><strong>${u.nome}</strong></td><td>${u.usuario}</td><td>${PERFIL[u.perfil]}</td>
        <td>${!u.ativo ? 'Bloqueado' : u.trocar_senha ? 'Senha provisória' : 'Liberado'}</td>
        <td class="acoes"><button class="botao-icone" aria-label="Editar ${u.nome}" title="Editar"
          onClick=${() => setEditando({ pessoa: u })}><${Icone} nome="lapis" tamanho=${18} /></button>
          <button class="botao-icone botao-perigo" aria-label="Excluir ${u.nome}" title="Excluir"
            onClick=${() => excluir(u)}><${Icone} nome="lixeira" tamanho=${18} /></button></td>
      </tr>`)}</tbody>
    </table></div></section>
    ${editando && html`<${FormularioPessoa} pessoa=${editando.pessoa} aoSalvar=${() => { setEditando(null); recarregar(); }}
      aoFechar=${() => setEditando(null)} />`}
  </div>`;
}

// ---------- Privacidade (LGPD) ----------

function Privacidade() {
  const { dados, erro, recarregar } = useDados('/api/admin/privacidade');
  const [f, setF] = useState(null);
  useEffect(() => { if (dados && !f) setF(dados); }, [dados]);
  if (!f) return html`<div class="secao"><p class="carregando">${erro || 'Carregando…'}</p></div>`;
  const campo = (nome) => (e) => setF({ ...f, [nome]: e.target.value });
  const salvar = async (e) => {
    e.preventDefault();
    if (await executar(() => api('/api/admin/privacidade', { metodo: 'PUT', corpo: f }), 'Aviso de privacidade atualizado')) recarregar();
  };
  return html`<div class="secao">
    <header class="secao-topo">
      <h1>Privacidade</h1>
      <a class="botao botao-contorno" href="/privacidade" target="_blank" rel="noopener">Ver o aviso publicado</a>
    </header>
    <section class="painel">
      <header class="painel-topo"><h2>Dados da empresa no aviso de privacidade</h2></header>
      <form class="formulario formulario-privacidade" onSubmit=${salvar}>
        <label class="rotulo" for="e-nome">Razão social ou nome da empresa</label>
        <input id="e-nome" class="campo" value=${f.empresa_nome} onInput=${campo('empresa_nome')} maxlength="120"
          placeholder="La Giovanna Pizzaria e Cafeteria Ltda." />
        <label class="rotulo" for="e-cnpj">CNPJ</label>
        <input id="e-cnpj" class="campo" value=${f.empresa_cnpj} onInput=${campo('empresa_cnpj')} maxlength="20"
          placeholder="00.000.000/0001-00" />
        <label class="rotulo" for="e-contato">Contato para assuntos de privacidade</label>
        <input id="e-contato" class="campo" value=${f.empresa_contato} onInput=${campo('empresa_contato')} maxlength="160"
          placeholder="privacidade@lagiovanna.com.br ou (00) 00000-0000" />
        <p class="grupo-nota">Esse contato aparece no aviso para clientes e equipe pedirem acesso, correção ou exclusão de dados.</p>
        <button class="botao botao-primario">Salvar</button>
      </form>
    </section>
    <section class="painel">
      <header class="painel-topo"><h2>O que o sistema já faz</h2></header>
      <ul class="lista-lgpd">
        <li>Não pede nome, telefone, e-mail ou CPF do cliente, e não usa cookies de rastreamento.</li>
        <li>Apaga as observações dos pedidos 30 dias depois do fechamento da conta.</li>
        <li>Guarda as senhas da equipe cifradas e exige senha individual, criada pela própria pessoa.</li>
        <li>Em Equipe, o botão Excluir apaga o nome e o usuário de quem saiu, mantendo só o histórico de vendas.</li>
      </ul>
    </section>
  </div>`;
}

// ---------- Moldura ----------

const TELAS = { resumo: Resumo, caixa: Caixa, cardapio: CardapioAdmin, mesas: Mesas, equipe: Equipe, privacidade: Privacidade };

function Admin() {
  const lerHash = () => (TELAS[location.hash.slice(1)] ? location.hash.slice(1) : 'resumo');
  const [secao, setSecao] = useState(lerHash);
  const [pendencias, setPendencias] = useState(0);
  useEffect(() => {
    const aoMudar = () => { setSecao(lerHash()); window.scrollTo(0, 0); };
    window.addEventListener('hashchange', aoMudar);
    return () => window.removeEventListener('hashchange', aoMudar);
  }, []);

  const contar = async () => {
    try { setPendencias((await api('/api/mesas')).filter((m) => m.chamado === 'conta').length); } catch { /* segue sem o contador */ }
  };
  useEffect(() => { contar(); }, []);
  useEventos(['pedidos', 'mesas'], contar);

  const Tela = TELAS[secao];
  const sair = async () => { await api('/api/logout', { metodo: 'POST' }); location.href = '/entrar'; };

  return html`<div class="admin">
    <aside class="admin-lateral">
      <div class="bandeira" aria-hidden="true"></div>
      <${Letreiro} classe="letreiro-pequeno" />
      <nav class="admin-nav" aria-label="Seções da gerência">
        ${SECOES.map(([id, rotulo]) => html`<a key=${id} href="#${id}" class=${secao === id ? 'ativa' : ''} aria-current=${secao === id ? 'page' : null}>
          ${rotulo}${id === 'caixa' && pendencias > 0 && html`<span class="contador" title="Mesas pedindo a conta">${pendencias}</span>`}</a>`)}
      </nav>
      <div class="admin-atalhos">
        <a href="/garcom">Tela do garçom</a>
        <a href="/cozinha">Tela da cozinha</a>
        <a href="/trocar-senha">Trocar minha senha</a>
      </div>
      <div class="admin-usuario">
        <span>${USUARIO.nome}</span>
        <button class="botao botao-fantasma" onClick=${sair}><${Icone} nome="sair" tamanho=${18} /> Sair</button>
      </div>
    </aside>
    <main class="admin-conteudo"><${Tela} /></main>
  </div>`;
}

iniciar(Admin);
