"""
Formtools Preview application.
"""
from django.http import Http404
from django.shortcuts import render
from django.utils.crypto import constant_time_compare

from .utils import form_hmac

AUTO_ID = 'formtools_%s'  # Each form here uses this as its auto_id parameter.


class FormPreview:
    preview_template = 'formtools/preview.html'
    form_template = 'formtools/form.html'

    # METHODS SUBCLASSES SHOULDN'T OVERRIDE ###################################

    def __init__(self, form):
        # form should be a Form class, not an instance.
        self.form, self.state = form, {}

    def __call__(self, request, *args, **kwargs):
        stage = {
            '1': 'preview',
            '2': 'post',
        }.get(request.POST.get(self.unused_name('stage')), 'preview')
        self.parse_params(request, *args, **kwargs)
        try:
            method = getattr(self, stage + '_' + request.method.lower())
        except AttributeError:
            raise Http404
        return method(request)

    def unused_name(self, name):
        """
        Given a first-choice name, adds an underscore to the name until it
        reaches a name that isn't claimed by any field in the form.

        This is calculated rather than being hard-coded so that no field names
        are off-limits for use in the form.
        """
        while 1:
            try:
                self.form.base_fields[name]
            except KeyError:
                break  # This field name isn't being used by the form.
            name += '_'
        return name

    def preview_get(self, request):
        "Displays the form"
        f = self.form(auto_id=self.get_auto_id(),
                      initial=self.get_initial(request),
                      **self.form_extra_params(request))
        return render(request, self.form_template, self.get_context(request, f))

    def preview_post(self, request):
        """
        Validates the POST data. If valid, displays the preview page.
        Else, redisplays form.
        """
        # Even if files are not supported in preview, we still initialize files
        # to give a chance to process_preview to access files content.
        f = self.form(data=request.POST,
                      files=request.FILES,
                      auto_id=self.get_auto_id(),
                      **self.form_extra_params(request))
        context = self.get_context(request, f)
        if f.is_valid():
            self.process_preview(request, f, context)
            context['hash_field'] = self.unused_name('hash')
            context['hash_value'] = self.security_hash(request, f)
            return render(request, self.preview_template, context)
        else:
            return render(request, self.form_template, context)

    def _check_security_hash(self, token, request, form):
        expected = self.security_hash(request, form)
        return constant_time_compare(token, expected)

    def post_post(self, request):
        """
        Validates the POST data. If valid, calls done(). Else, redisplays form.
        """
        form = self.form(request.POST, auto_id=self.get_auto_id(), **self.form_extra_params(request))
        if form.is_valid():
            if not self._check_security_hash(
                    request.POST.get(self.unused_name('hash'), ''),
                    request, form):
                return self.failed_hash(request)  # Security hash failed.
            return self.done(request, form.cleaned_data)
        else:
            return render(request, self.form_template, self.get_context(request, form))

    # METHODS SUBCLASSES MIGHT OVERRIDE IF APPROPRIATE ########################

    def get_auto_id(self):
        """
        Hook to override the ``auto_id`` kwarg for the form. Needed when
        rendering two form previews in the same template.
        """
        return AUTO_ID

    def get_initial(self, request):
        """
        Takes a request argument and returns a dictionary to pass to the form's
        ``initial`` kwarg when the form is being created from an HTTP get.
        """
        return {}

    def get_context(self, request, form):
        "Context for template rendering."
        return {
            'form': form,
            'stage_field': self.unused_name('stage'),
            'state': self.state,
        }

    def parse_params(self, request, *args, **kwargs):
        """
        Given captured args and kwargs from the URLconf, saves something in
        self.state and/or raises :class:`~django.http.Http404` if necessary.

        For example, this URLconf captures a user_id variable::

            path('contact/<int:user_id>/', MyFormPreview(MyForm)),

        In this case, the kwargs variable in parse_params would be
        ``{'user_id': 32}`` for a request to ``'/contact/32/'``. You can use
        that ``user_id`` to make sure it's a valid user and/or save it for
        later, for use in :meth:`~formtools.preview.FormPreview.done()`.
        """
        pass

    def process_preview(self, request, form, context):
        """
        Given a validated form, performs any extra processing before displaying
        the preview page, and saves any extra data in context.

        By default, this method is empty.  It is called after the form is
        validated, but before the context is modified with hash information
        and rendered.
        """
        pass

    def security_hash(self, request, form):
        """
        Calculates the security hash for the given
        :class:`~django.http.HttpRequest` and :class:`~django.forms.Form`
        instances.

        Subclasses may want to take into account request-specific information,
        such as the IP address.
        """
        return form_hmac(form)

    def failed_hash(self, request):
        """
        Returns an :class:`~django.http.HttpResponse` in the case of
        an invalid security hash.
        """
        return self.preview_post(request)

    def form_extra_params(self, request):
        """
        Extra parameters to pass to the form constructor.
        Returns a dictionary.
        By default, returns an empty dictionary.
        """
        return {}

    # METHODS SUBCLASSES MUST OVERRIDE ########################################

    def done(self, request, cleaned_data):
        """
        Does something with the ``cleaned_data`` data and then needs to
        return an :class:`~django.http.HttpResponseRedirect`, e.g. to a
        success page.
        """
        raise NotImplementedError('You must define a done() method on your '
                                  '%s subclass.' % self.__class__.__name__)
