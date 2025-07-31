from meta.views import Meta

def default_meta(request):
    return {
        'meta': Meta(
            title="Atlas Competition",
            description="Atlas Competition is the all-in-one platform for managing and competing in strongman events. Discover upcoming competitions, register online, track scores live, and showcase athlete profiles. All in one place.",
            url=request.build_absolute_uri(),
            image="https://atlascompetition.com/static/images/navabarlogo.png",
            object_type='website',
            site_name='Atlas Competition',
        )
    }
