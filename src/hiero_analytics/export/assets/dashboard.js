
function filterTable(id,q){q=q.toLowerCase();var n=0,rows=document.querySelectorAll('#'+id+' tbody tr');rows.forEach(function(tr){var hit=tr.textContent.toLowerCase().indexOf(q)>-1;tr.style.display=hit?'':'none';if(hit)n++;});var c=document.getElementById(id+'-count');if(c)c.textContent=n+' rows';}
function sortTable(id,col,th){var tb=document.querySelector('#'+id+' tbody');var rows=Array.prototype.slice.call(tb.querySelectorAll('tr'));var asc=th.getAttribute('data-dir')!=='asc';th.setAttribute('data-dir',asc?'asc':'desc');var num=/^-?\d+(?:\.\d+)?$/;rows.sort(function(a,b){var x=a.children[col].textContent.trim(),y=b.children[col].textContent.trim();if(num.test(x)&&num.test(y))return asc?x-y:y-x;return asc?x.localeCompare(y):y.localeCompare(x);});rows.forEach(function(r){tb.appendChild(r);});}
/* Spreadsheet apps evaluate any cell whose text opens with =, +, - or @ (also tab
   and CR), so a GitHub-sourced value such as a repo description reading
   "=HYPERLINK(...)" or a login "@someone" becomes a live formula the moment the
   download is opened. CSV quoting does not prevent this — Excel and Sheets parse
   the quotes off and evaluate what is inside — so the cell text itself has to be
   defused with a leading apostrophe, which spreadsheets read as "treat as text".
   Plain numbers are exempt so a negative value stays numeric instead of becoming
   a text cell that will not sum. */
function csvCell(s){s=(s==null?'':String(s)).trim();if(/^[=+\-@\t\r]/.test(s)&&!/^-?\d+(?:\.\d+)?$/.test(s))s="'"+s;return /[",\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s;}
/* A downloaded CSV leaves the dashboard behind: no "data as of" badge, no page
   header, no way back to the run that produced it. Worse, the export takes the
   *visible* rows, so a filtered download is a subset that looks identical to the
   full table once it is sitting in someone's Downloads folder. The preamble is
   what keeps that file honest — it names the view, the data watermark, the code
   revision, and how many of the total rows actually came along. */
function csvComment(s){return '# '+String(s).replace(/[\r\n]+/g,' ');}
function csvPreamble(table,id,shown){
  var prov=(typeof PROVENANCE==='undefined')?{}:PROVENANCE;
  var title=table.getAttribute('data-title')||'';
  var asof=table.getAttribute('data-asof')||'';
  var total=parseInt(table.getAttribute('data-total')||'0',10)||shown;
  var q=document.getElementById(id+'-q');
  var query=q&&q.value?q.value.trim():'';
  var lines=[csvComment('Hiero analytics'+(title?' — '+title:''))];
  var stamp=[];
  if(asof)stamp.push('data as of '+asof);
  if(prov.sha)stamp.push('code '+prov.sha);
  if(stamp.length)lines.push(csvComment(stamp.join(' · ')));
  /* Say "N of M" only when they differ, so an unfiltered export reads cleanly.
     The query is quoted only when there is one: rows can be hidden with an empty
     box, and 'filtered: ""' reads like a bug rather than a fact. */
  lines.push(csvComment(shown===total?total+' rows':shown+' of '+total+' rows'+(query?' (filtered: "'+query+'")':' (filtered)')));
  lines.push(csvComment('exported '+new Date().toISOString().replace('T',' ').slice(0,16)+' UTC'+(prov.generated?' from a dashboard generated '+prov.generated:'')));
  return lines;
}
function exportCSV(id,name){var table=document.getElementById(id);var body=[];var ths=document.querySelectorAll('#'+id+' thead th');body.push([].map.call(ths,function(th){return csvCell(th.textContent);}).join(','));var shown=0;document.querySelectorAll('#'+id+' tbody tr').forEach(function(tr){if(tr.style.display==='none')return;shown++;body.push([].map.call(tr.children,function(td){return csvCell(td.textContent);}).join(','));});var out=csvPreamble(table,id,shown).concat(body);var blob=new Blob([out.join('\n')],{type:'text/csv'});var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;document.body.appendChild(a);a.click();document.body.removeChild(a);URL.revokeObjectURL(a.href);}
function switchMacro(m){document.querySelectorAll('.macropanel').forEach(function(p){p.style.display='none';});document.getElementById('macro-'+m).style.display='';document.querySelectorAll('.macro').forEach(function(b){b.classList.remove('active');});document.getElementById('macrobtn-'+m).classList.add('active');}
/* The macro tabs are real links (#contributors, #governance, ...): the hash is
   the source of truth, so tabs are shareable and back/forward work. Hashes that
   don't name a macro panel (e.g. the jump-bar's section anchors) are left to
   native anchor behaviour. */
function applyMacroHash(){var slug=location.hash.replace(/^#/,'');if(document.getElementById('macro-'+slug))switchMacro(slug);}
window.addEventListener('hashchange',applyMacroHash);
applyMacroHash();
function switchTab(m,o){var panel=document.getElementById('macro-'+m);panel.querySelectorAll('.tabpanel').forEach(function(p){p.style.display='none';});document.getElementById('tab-'+m+'-'+o).style.display='';panel.querySelectorAll('.tab').forEach(function(b){b.classList.remove('active');});document.getElementById('tabbtn-'+m+'-'+o).classList.add('active');}
function openLightbox(el){var src=(typeof el==='string')?el:el.src;document.getElementById('lightbox-img').src=src;var info='';if(el&&el.closest){var fig=el.closest('figure');if(fig){var di=el.getAttribute?el.getAttribute('data-i'):null;var n=(di!=null)?fig.querySelector(".lbinfo[data-i='"+di+"']"):null;if(!n)n=fig.querySelector('.lbinfo:not([data-i])');if(n)info=n.innerHTML;}}document.getElementById('lightbox-note').innerHTML=info;document.getElementById('lightbox').style.display='flex';}
function closeLightbox(){var lb=document.getElementById('lightbox');lb.style.display='none';document.getElementById('lightbox-img').src='';document.getElementById('lightbox-note').innerHTML='';}
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeLightbox();});
function slide(id,dir){var s=document.querySelectorAll('#'+id+'-show .slide');if(!s.length)return;var cur=0;s.forEach(function(f,i){if(f.style.display!=='none')cur=i;});s[cur].style.display='none';var n=(cur+dir+s.length)%s.length;s[n].style.display='';var c=document.getElementById(id+'-counter');if(c)c.textContent=(n+1)+' / '+s.length;}
function chartTab(btn,i){var fig=btn.closest('figure');if(!fig)return;fig.querySelectorAll('.ctab').forEach(function(b,j){b.classList.toggle('active',j===i);});fig.querySelectorAll('.cimg').forEach(function(img){img.style.display=(+img.getAttribute('data-i')===i)?'':'none';});}
function periodTab(btn,i){var section=btn.closest('.tsec');if(!section)return;section.querySelectorAll('.periodtab').forEach(function(b,j){b.classList.toggle('active',j===i);});section.querySelectorAll('.periodview').forEach(function(view,j){view.style.display=j===i?'':'none';});}

/* HIP coverage matrix: click a cell to list the PRs behind its count. The data
   is a JSON blob rendered next to the matrix ("<hip>|<repo>" -> PR rows), so
   the panel works fully offline like everything else on this page. */
var __hipEv=null,__hipEvTd=null;
function hipEv(td,hip,repo){
  if(__hipEv===null){var el=document.getElementById('hip-ev-data');__hipEv=el?JSON.parse(el.textContent||'{}'):{};}
  var rows=__hipEv[hip+'|'+repo];var panel=document.getElementById('hip-ev-panel');
  if(!rows||!panel)return;
  if(__hipEvTd===td){hipEvClose();return;}
  if(__hipEvTd)__hipEvTd.classList.remove('sel');
  __hipEvTd=td;td.classList.add('sel');
  document.getElementById('hip-ev-title').textContent='HIP-'+hip+' · '+repo;
  document.getElementById('hip-ev-count').textContent=rows.length+' referencing PR'+(rows.length>1?'s':'');
  var list=document.getElementById('hip-ev-list');list.textContent='';
  rows.forEach(function(r){
    var li=document.createElement('li'),l1=document.createElement('div');l1.className='l1';
    var a=document.createElement('a');a.href='https://github.com/'+repo+'/pull/'+r.n;a.target='_blank';a.rel='noopener';a.textContent='#'+r.n;
    var t=document.createElement('span');t.className='t';t.textContent=r.t;
    var d=document.createElement('span');d.className='meta';d.textContent=r.st==='MERGED'?'merged '+r.d:r.st.toLowerCase();
    var m=document.createElement('span');m.className='meta';m.textContent='matched in: '+r.m.split('|').join(', ');
    l1.appendChild(a);l1.appendChild(t);l1.appendChild(d);l1.appendChild(m);
    if(r.q){var q=document.createElement('span');q.className='cue';q.textContent='not counted — “'+r.q+'”';l1.appendChild(q);}
    li.appendChild(l1);
    if(r.x){var x=document.createElement('div');x.className='snip';x.textContent=r.x;li.appendChild(x);}
    list.appendChild(li);
  });
  panel.hidden=false;panel.scrollIntoView({block:'nearest',behavior:'smooth'});
}
function hipEvClose(){
  var panel=document.getElementById('hip-ev-panel');if(panel)panel.hidden=true;
  if(__hipEvTd){__hipEvTd.classList.remove('sel');__hipEvTd=null;}
}
document.addEventListener('keydown',function(ev){
  if((ev.key==='Enter'||ev.key===' ')&&ev.target.classList&&ev.target.classList.contains('ck')){ev.preventDefault();ev.target.click();}
  if(ev.key==='Escape')hipEvClose();
});

/* Matrix filters: free text and a governance-status pill, combined. */
var __mxq='',__mxs='';
function hipMxApply(){
  var n=0;document.querySelectorAll('#hip-matrix-tbl tbody tr').forEach(function(tr){
    var st=tr.querySelector('td.hipmx-status');st=st?st.textContent:'';
    var hit=(__mxs===''||st===__mxs)&&(__mxq===''||tr.textContent.toLowerCase().indexOf(__mxq)>-1);
    tr.style.display=hit?'':'none';if(hit)n++;});
  var c=document.getElementById('hip-matrix-tbl-count');if(c)c.textContent=n+' rows';
}
function hipMxFilter(q){__mxq=(q||'').toLowerCase();hipMxApply();}
function hipMxStatus(btn){
  var s=btn.getAttribute('data-s');__mxs=(__mxs===s?'':s);
  document.querySelectorAll('.hipmx-fbtn').forEach(function(b){b.classList.toggle('active',b.getAttribute('data-s')===__mxs);});
  hipMxApply();
}

/* Governance board: a chip jumps to (and flashes) the HIP's matrix row,
   clearing any matrix filters that would hide it. */
function hipBoardJump(hip){
  __mxq='';__mxs='';
  var mx=document.getElementById('hip-matrix-tbl');
  if(mx){var wrap=mx.closest('.sbody');if(wrap){var inp=wrap.querySelector('.search');if(inp)inp.value='';}}
  document.querySelectorAll('.hipmx-fbtn').forEach(function(b){b.classList.remove('active');});
  hipMxApply();
  var row=document.getElementById('hipmx-row-'+hip);
  if(!row)return;
  row.scrollIntoView({block:'center',behavior:'smooth'});
  row.classList.add('flash');
  setTimeout(function(){row.classList.remove('flash');},1800);
}

/* Board chip click: show the spec's title/status in the info bar; the bar's
   button jumps to the matrix row. */
var __hipPick=null;
function hipBoardPick(btn,hip){
  document.querySelectorAll('.hipchip.active').forEach(function(b){b.classList.remove('active');});
  var bar=document.getElementById('hip-board-info');
  if(__hipPick===btn){bar.hidden=true;__hipPick=null;return;}
  __hipPick=btn;btn.classList.add('active');
  document.getElementById('hip-board-info-num').textContent='HIP-'+hip;
  document.getElementById('hip-board-info-title').textContent=btn.getAttribute('data-t')||'';
  document.getElementById('hip-board-info-status').textContent=btn.getAttribute('data-st')||'';
  document.getElementById('hip-board-info-jump').onclick=function(){hipBoardJump(hip);};
  bar.hidden=false;
}
