"""学生 1 相关表单：注册、登录、会员档案、角色权限。"""
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db import transaction

from .models import Member, User


class StyledFormMixin:
    """统一给表单控件加 Bootstrap 样式。"""

    def apply_style(self):
        for name, field in self.fields.items():
            widget = field.widget
            css = "form-control"
            if isinstance(widget, forms.CheckboxInput):
                css = "form-check-input"
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css = "form-select"
            elif isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("rows", 3)
            existing = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{existing} {css}".strip()
            if isinstance(widget, forms.DateInput):
                widget.input_type = "date"
            if field.required and not isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("required", "required")


class LoginForm(StyledFormMixin, AuthenticationForm):
    username = forms.CharField(label="登录账号", widget=forms.TextInput(
        attrs={"placeholder": "请输入用户名 / 手机号", "autofocus": True}))
    password = forms.CharField(label="登录密码", widget=forms.PasswordInput(
        attrs={"placeholder": "请输入密码"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_style()
        self.fields["username"].widget.attrs["class"] = "form-control"


class MemberRegisterForm(StyledFormMixin, UserCreationForm):
    """会员注册：同时创建登录账号与会员档案。"""

    display_name = forms.CharField(label="姓名", max_length=30)
    phone = forms.CharField(label="手机号", max_length=20)
    gender = forms.ChoiceField(label="性别", choices=Member.GENDER_CHOICES, initial="U")
    birthday = forms.DateField(label="出生日期", required=False, widget=forms.DateInput())
    constitution = forms.CharField(label="中医体质", max_length=30, required=False,
                                   widget=forms.TextInput(attrs={"placeholder": "如 气虚质（不确定可留空）"}))
    health_notes = forms.CharField(label="健康诉求", required=False, widget=forms.Textarea())

    class Meta:
        model = User
        fields = ("username", "display_name", "phone", "gender", "birthday",
                  "constitution", "health_notes")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_style()
        self.fields["username"].label = "登录账号"
        self.fields["username"].widget.attrs["placeholder"] = "3-20 位字母或数字"
        self.fields["password1"].label = "登录密码"
        self.fields["password2"].label = "确认密码"

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if not (phone.isdigit() and len(phone) == 11):
            raise forms.ValidationError("请输入 11 位手机号")
        if Member.objects.filter(phone=phone).exists():
            raise forms.ValidationError("该手机号已注册会员")
        return phone

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = "member"
        user.display_name = self.cleaned_data["display_name"]
        user.phone = self.cleaned_data["phone"]
        user.save()
        Member.objects.create(
            user=user,
            name=self.cleaned_data["display_name"],
            gender=self.cleaned_data["gender"],
            birthday=self.cleaned_data.get("birthday"),
            phone=self.cleaned_data["phone"],
            constitution=self.cleaned_data.get("constitution", ""),
            health_notes=self.cleaned_data.get("health_notes", ""),
            created_by=user,
        )
        return user


class MemberForm(StyledFormMixin, forms.ModelForm):
    """员工维护会员档案。"""

    class Meta:
        model = Member
        fields = ["name", "gender", "birthday", "phone", "level", "points", "balance",
                  "constitution", "health_notes", "allergy", "tags", "is_active", "remark"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_style()

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        qs = Member.objects.filter(phone=phone)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("该手机号已被其他会员使用")
        return phone


class MemberProfileForm(StyledFormMixin, forms.ModelForm):
    """会员本人可维护的基础资料（等级、积分、余额等由员工维护）。"""

    class Meta:
        model = Member
        fields = ["name", "gender", "birthday", "phone", "constitution", "allergy", "health_notes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_style()

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if Member.objects.exclude(pk=self.instance.pk).filter(phone=phone).exists():
            raise forms.ValidationError("该手机号已被其他会员使用")
        return phone


class UserRoleForm(StyledFormMixin, forms.ModelForm):
    """管理员分配用户角色与附加权限组。"""

    class Meta:
        model = User
        fields = ["display_name", "phone", "role", "groups", "is_active"]
        widgets = {"groups": forms.SelectMultiple(attrs={"size": 6})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_style()
        self.fields["groups"].help_text = "角色决定默认权限组，可按需追加附加权限组"
