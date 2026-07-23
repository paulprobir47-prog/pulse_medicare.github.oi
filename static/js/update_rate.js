document.addEventListener('DOMContentLoaded', function(){
  function $(s){return document.querySelector(s)}
  const catButtons = document.querySelectorAll('.cat-btn')
  catButtons.forEach(b=>{
    b.addEventListener('click', ()=>{
      const id = b.dataset.id
      const name = b.dataset.name
      const rate = b.dataset.rate
      const catId = document.getElementById('category_id')
      const catName = document.getElementById('category_name')
      const newRate = document.getElementById('new_rate')
      if(catId) catId.value = id
      if(catName) catName.value = name
      if(newRate) newRate.value = rate
      window.scrollTo({top:0,behavior:'smooth'})
    })
  })
})

function clearFilters(){
  const f = document.getElementById('searchForm')
  if(!f) return
  f.querySelectorAll('input[type="search"]').forEach(i=>i.value='')
  f.querySelectorAll('select').forEach(s=>s.selectedIndex=0)
  f.submit()
}
