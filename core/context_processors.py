from meta.views import Meta

def default_meta(request):
    return {
        'meta': Meta(
            title="Atlas Competition",
            description="Built for the future of strength sports.",
            url=request.build_absolute_uri(),
            image="https://atlascompetition.com/static/images/logo.png",
            object_type='website',
            site_name='Atlas Competition',
        )
    }
