import re

from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexers import get_all_lexers, get_lexer_by_name

from wagtail.core.blocks import (BooleanBlock, CharBlock, ChoiceBlock, IntegerBlock, ListBlock, RichTextBlock,
                                 StructBlock, TextBlock)
from wagtail.core.blocks.stream_block import StreamBlock
from wagtail.documents.blocks import DocumentChooserBlock
from wagtail.embeds.blocks import EmbedBlock
from wagtail.images.blocks import ImageChooserBlock


class CodeBlock(StructBlock):
    code = TextBlock()
    language = ChoiceBlock(choices=[(name, name) for name in sorted(lexer[1][0] for lexer in get_all_lexers())],
                           required=False)

    def get_context(self, value, parent_context=None):
        context = super().get_context(value, parent_context=parent_context)

        if value['language']:
            lexer = get_lexer_by_name(value['language'])
            formatter = HtmlFormatter(lineseparator='<br/>', nowrap=True, nobackground=True)
            context['highlighted_code'] = highlight(value['code'], lexer, formatter)

        return context

    class Meta:
        icon = 'code'
        template = 'blog/blocks/code.html'


class MathBlock(TextBlock):
    """
    For non-inline math, which may have special layout considerations.
    """
    class Meta:
        icon = 'plus'
        template = 'blog/blocks/math.html'


class CleanedRichTextBlock(RichTextBlock):
    """
    Rich text block that cleans up some artifacts the rich text editor
    tends to leave behind (empty paragraphs and non-breaking spaces).
    """
    def value_from_form(self, value):
        value = value.replace('\xa0', ' ')
        value = re.sub(r'<p>\s*</p>', r'', value)
        return super().value_from_form(value)


class RichTextWithCodeBlock(CleanedRichTextBlock):
    """
    Rich text block that translates square-bracket code tags into the HTML
    equivalent for display purposes. We could mess with the editor to get it
    to support inline code, but this is a lot easier.
    """
    def value_for_form(self, value):
        value = super().value_for_form(value)
        return re.sub(r'<(/?)code>', r'[\1code]', value)

    def value_from_form(self, value):
        value = re.sub(r'\[(/?)code\]', r'<\1code>', value)
        return super().value_from_form(value)


class ImageRowBlock(StructBlock):
    images = ListBlock(StructBlock([
        ('image', ImageChooserBlock()),
        ('weight', IntegerBlock(min_value=1, max_value=99, default=1,
                                help_text='How much space to allocate to this image relative to others'))
    ]))
    caption = CharBlock(required=False)

    class Meta:
        icon = 'image'
        template = 'blog/blocks/image_row.html'


class FullBleedImageBlock(StructBlock):
    image = ImageChooserBlock()
    caption = CharBlock(required=False)
    add_parallax = BooleanBlock()

    class Meta:
        icon = 'image'
        template = 'blog/blocks/full_bleed_image.html'


class ContentBlock(StreamBlock):
    text = RichTextWithCodeBlock(template='blog/blocks/rich_text.html')
    code = CodeBlock()
    math = MathBlock()
    image_row = ImageRowBlock()
    full_bleed_image = FullBleedImageBlock()
    embed = EmbedBlock()
    document = DocumentChooserBlock()


class ContentMethodsMixin(object):
    content_field_name = 'body'

    @property
    def content_field(self):
        return getattr(self, self.content_field_name)

    def first_text_block(self):
        try:
            return next(self.all_text_blocks())
        except StopIteration:
            return None

    def all_text_blocks(self):
        return (block for block in self.content_field if isinstance(block.block, RichTextBlock))

    def first_text_block_is_all_there_is(self):
        return (len(self.content_field) - int(self.first_text_block() is not None)) == 0

    def contains_math(self):
        return any(self.block_contains_math(block) for block in self.content_field)

    @staticmethod
    def block_contains_math(block):
        return isinstance(block.block, MathBlock) or (isinstance(block.block, RichTextBlock) and
                re.search(r'(?:\\\[.*\\\])|(?:\\\(.*\\\))', block.value.source) is not None)

    def contains_code(self):
        return any(isinstance(block.block, CodeBlock) for block in self.content_field)
