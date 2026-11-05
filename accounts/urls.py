from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    # ① 注册 / 登录 / 退出
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", views.UserLoginView.as_view(), name="login"),
    path("logout/", views.UserLogoutView.as_view(), name="logout"),
    # ② 会员中心与档案维护
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("members/", views.MemberListView.as_view(), name="member_list"),
    path("members/create/", views.MemberCreateView.as_view(), name="member_create"),
    path("members/<int:pk>/", views.MemberDetailView.as_view(), name="member_detail"),
    path("members/<int:pk>/edit/", views.MemberUpdateView.as_view(), name="member_update"),
    # ③ 角色、菜单与接口权限
    path("roles/", views.RoleListView.as_view(), name="role_list"),
    path("roles/<int:pk>/permissions/", views.RolePermissionView.as_view(), name="role_permission"),
    path("users/", views.UserListView.as_view(), name="user_list"),
    path("users/<int:pk>/role/", views.UserRoleUpdateView.as_view(), name="user_role"),
]
