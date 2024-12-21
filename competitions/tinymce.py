TINYMCE_DEFAULT_CONFIG = {
    'height': 360,
    'width': 1140,
    'cleanup_on_startup': True,
    'custom_undo_redo_levels': 20,
    'selector': 'textarea',
    'theme': 'modern',
    'plugins': '''
        textcolor save link image media preview codesample contextmenu
        table code lists fullscreen insertdatetime  
 nonbreaking
        contextmenu directionality searchreplace wordcount visualblocks
        visualchars code fullscreen autolink lists charmap print hr
        anchor pagebreak
        ''',
    'toolbar1': '''
        fullscreen preview bold italic underline | fontselect,
        fontsizeselect | forecolor backcolor | alignleft aligncenter  

        alignright alignjustify | bullist numlist outdent indent |
        link image  
 media | codesample |
        ''',
    'contextmenu': 'formats | link image',
    'menubar': True,
    'statusbar': True,
}
