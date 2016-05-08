// I'm pulling in ~90kb of javascript (i.e. jQuery, mostly unused) to
// add a parallax effect to the hero image with the following eight
// lines of code. The alternatives were a) scrapping the parallax or
// b) taking the time to figure out browser compatibility myself, both
// of which were obviously out of the question. SORRY EVERYONE

$(function() {
    var doc = $(document), hero = $('#hero');
    if (!hero.hasClass('with_image')) return;
    doc.on('scroll', function(event) {
        var offset = Math.max(0, doc.scrollTop() / 3);
        hero.css({'background-position': '50% ' + offset + 'px'})
    });
});
